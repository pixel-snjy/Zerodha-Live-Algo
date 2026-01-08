from pathlib import Path
import time
from typing import cast, Optional, Dict, Any
from urllib.parse import urlparse, parse_qs
import mibian

import pandas as pd
# import polars as pl
import requests
from kiteconnect import KiteConnect


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Send a formatted message to a Telegram chat using a bot.
    
    Args:
        bot_token: Telegram bot token for authentication
        chat_id: ID of the chat to send the message to
        text: Message text to send (supports HTML formatting)
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            error_msg = f"{e.response.status_code} {e.response.reason}"
        print(f"Telegram send error: {error_msg}")
        return False

def get_telegram_updates(bot_token: str, offset: Optional[int] = None, poll_timeout: int = 10) -> Dict[str, Any]:
    """Fetch new messages from the Telegram bot.
    
    Args:
        bot_token: Telegram bot token for authentication
        offset: Identifier of the first update to be returned
        
    Returns:
        Dict containing the updates or error information
    """
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {'timeout': poll_timeout}
    if offset is not None:
        params['offset'] = offset + 1
    
    try:
        response = requests.get(url, params=params, timeout=poll_timeout + 5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching Telegram updates: {e}")
        return {"ok": False, "result": []}

def _wait_for_redirect_url(bot_token: str, chat_id: str, timeout: int = 300) -> str:
    """Wait for user to send the redirect URL with request token via Telegram.
    
    Args:
        bot_token: Telegram bot token for sending/receiving messages
        chat_id: Telegram chat ID to communicate with the user
        timeout: Maximum time to wait for response in seconds
        
    Returns:
        str: The redirect URL containing the request token
        
    Raises:
        TimeoutError: If no valid URL is received within the timeout period
    """
    last_update_id = None
    start_time = time.time()

    # Drain any previous (old) updates so we only receive fresh messages after this call
    try:
        existing = get_telegram_updates(bot_token, offset=None, poll_timeout=1)
        if existing.get("ok") and existing.get("result"):
            # mark last_update_id as the highest seen update_id so older messages are ignored
            last_update_id = max(u.get("update_id", 0) for u in existing["result"])
    except Exception:
        # If draining fails, continue without a last_update_id (we'll still poll normally)
        last_update_id = None
    
    while time.time() - start_time < timeout:
        updates = get_telegram_updates(bot_token, last_update_id, poll_timeout=5)
        
        if updates.get('ok') and updates.get('result'):
            for update in updates['result']:
                last_update_id = update.get('update_id', last_update_id)
                
                # Process only text messages
                # if 'message' in update and 'text' in update['message']:
                #     text = update['message']['text'].strip()
                message = update.get('message') or {}
                text = message.get('text')
                if not text:
                   continue
                text = text.strip()
                    
                    # Check for request token in the message
                if 'request_token=' in text or 'kite.trade/connect' in text or 'kite.zerodha.com/connect' in text:
                    return text
        
        time.sleep(2)  # Check for updates every 2 seconds
    
    # If we get here, we timed out
    error_msg = "❌ Timed out waiting for authentication URL. Please try again."
    send_telegram_message(bot_token, chat_id, error_msg)
    raise TimeoutError("Timed out waiting for redirect URL")

def _save_access_token(access_token: str, deps_dir: Path) -> None:
    """Save the access token to a file.
    
    Args:
        access_token: The access token to save
        deps_dir: Directory where the token file should be saved
        
    Raises:
        IOError: If the token cannot be saved or verified
    """
    deps_dir.mkdir(exist_ok=True)
    token_file = deps_dir / "access_token.txt"
    token_file.write_text(access_token)
    
    # Verify the token was saved correctly
    if not token_file.exists() or token_file.read_text().strip() != access_token:
        raise IOError("Failed to save access token")

def _download_instruments(kite: KiteConnect, bot_token: str, chat_id: str, deps_dir: Path) -> None:
    """Download and save market instruments data.
    
    Args:
        kite: Authenticated KiteConnect instance
        bot_token: Telegram bot token for sending updates
        chat_id: Telegram chat ID to send updates to
        deps_dir: Directory to save the instruments data
    """
    # send_telegram_message(bot_token, chat_id, "📥 Downloading instrument data...")
    
    exchanges = ['NSE', 'NFO', 'BSE', 'BFO', 'MCX']
    all_instruments = []
    
    # Fetch instruments for each exchange
    for exchange in exchanges:
        try:
            instruments = kite.instruments(exchange=exchange)
            all_instruments.extend(instruments)
            # send_telegram_message(bot_token, chat_id, 
            #                     f"✓ Fetched {len(instruments)} instruments from {exchange}")
        except Exception as e:
            error_msg = f"⚠ Could not fetch instruments for {exchange}: {str(e)}"
            send_telegram_message(bot_token, chat_id, error_msg)
    
    # Save instruments data if any were fetched
    if all_instruments:
        df = pd.DataFrame(all_instruments)
        df.to_csv(deps_dir / "tradeable_instruments.csv", index=False)
        success_msg = "✅ Successfully saved instrument file."
        send_telegram_message(bot_token, chat_id, success_msg)
    else:
        send_telegram_message(bot_token, chat_id, 
                            "⚠ No instruments were downloaded. Some functionality may be limited.")

def login(api_key: str, api_secret: str, bot_token: str, chat_id: str) -> KiteConnect | None:
    """
    Authenticate with KiteConnect using Telegram bot for interaction.
    
    This function handles the complete OAuth flow for KiteConnect:
    1. Generates and sends login URL via Telegram
    2. Waits for user to send back the redirect URL
    3. Extracts request token and generates access token
    4. Saves the access token and downloads market instruments
    
    Args:
        api_key: KiteConnect API key
        api_secret: KiteConnect API secret
        bot_token: Telegram bot token for sending/receiving messages
        chat_id: Telegram chat ID to communicate with the user
        
    Returns:
        KiteConnect: Authenticated KiteConnect instance
        
    Raises:
        ValueError: If authentication fails or required data is missing
        TimeoutError: If no response is received within expected time
        Exception: For other API or file system related errors
    """
    try:
        # Initialize KiteConnect with API key
        kite = KiteConnect(api_key=api_key)
        
        # Generate and send login URL via Telegram
        login_url = kite.login_url()

        """
        Automate the login flow using pyotp and selenium driver
        """

        auth_message = (
            "🔑 <b>KiteConnect Authentication Required</b>\n\n"
            f"1. Click this link to login: <a href='{login_url}'>Login to Kite</a>\n"
            "2. After login, you'll be redirected. Copy the complete URL from your browser's address bar.\n"
            "3. Paste the URL here to complete authentication."
        )
        send_telegram_message(bot_token, chat_id, auth_message)
        
        # Wait for user to send the redirect URL (1 minute timeout)
        redirect_url = _wait_for_redirect_url(bot_token, chat_id, timeout=300)
        
        # Parse request token from URL
        parsed_url = urlparse(redirect_url)
        parsed_params = parse_qs(parsed_url.query)
        request_token = parsed_params.get('request_token', [''])[0]
        
        if not request_token:
            error_msg = "❌ Invalid URL. Could not find request token. Please try again."
            send_telegram_message(bot_token, chat_id, error_msg)
            raise ValueError("Invalid redirect URL: No request token found")
        
        # Generate and save session
        send_telegram_message(bot_token, chat_id, "🔄 Generating session...")
        session = kite.generate_session(request_token, api_secret=api_secret)
        # kite.set_access_token(session['access_token'])
        
        # _save_access_token(session['access_token'], deps_dir)
        session_dict = cast(Dict[str, Any], session)
        access_token = session_dict.get("access_token")
        if not access_token:
            error_msg = "❌ Authentication failed: no access_token in session response"
            send_telegram_message(bot_token, chat_id, error_msg)
            raise ValueError("Invalid session: access_token missing")
        
        kite.set_access_token(str(access_token))

        # Save access token
        deps_dir = Path("src/Dependencies")
        _save_access_token(str(access_token), deps_dir)
        
        # Download market instruments
        _download_instruments(kite, bot_token, chat_id, deps_dir)
        
        send_telegram_message(bot_token, chat_id, "✅ <b>Authentication successful!</b> You're all set!")
        return kite
        
    except Exception as e:
        error_msg = f"❌ Authentication failed: {str(e)}"
        send_telegram_message(bot_token, chat_id, error_msg)
        raise


def convert_heikin_ashi(df):
    """
    Convert regular OHLC data to Heikin-Ashi candlesticks.

    Heikin-Ashi formulas:
    - HA_Close = (Open + High + Low + Close) / 4
    - HA_Open = (Previous HA_Open + Previous HA_Close) / 2
    - HA_High = max(High, HA_Open, HA_Close)
    - HA_Low = min(Low, HA_Open, HA_Close)

    Args:
        df: DataFrame with columns ['open', 'high', 'low', 'close', 'date', 'volume']

    Returns:
        DataFrame with Heikin-Ashi candlestick data
    """
    try:
        if df.empty:
            raise ValueError("Input DataFrame is empty.")

        # Ensure the DataFrame has the required columns
        required_columns = ['open', 'high', 'low', 'close', 'date']
        if not all(col in df.columns for col in required_columns):
            raise ValueError(f"Input DataFrame must contain these columns: {required_columns}")

        # Calculate Heikin-Ashi Close for all candles
        ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4

        # Initialize lists for Heikin-Ashi values
        ha_open = []
        ha_high = []
        ha_low = []

        # Calculate Heikin-Ashi values for each candle
        for i in range(len(df)):
            if i == 0:
                # First candle: HA_Open = regular Open
                ha_open_val = df['open'].iloc[0]
            else:
                # Subsequent candles: HA_Open = (Previous HA_Open + Previous HA_Close) / 2
                ha_open_val = (ha_open[-1] + ha_close.iloc[i - 1]) / 2

            # HA_High = max of regular High, HA_Open, HA_Close
            ha_high_val = max(df['high'].iloc[i], ha_open_val, ha_close.iloc[i])

            # HA_Low = min of regular Low, HA_Open, HA_Close
            ha_low_val = min(df['low'].iloc[i], ha_open_val, ha_close.iloc[i])

            # Append calculated values
            ha_open.append(ha_open_val)
            ha_high.append(ha_high_val)
            ha_low.append(ha_low_val)

        # Create Heikin-Ashi DataFrame
        ha_df = pd.DataFrame({
            'date': df['date'],
            'open': ha_open,
            'high': ha_high,
            'low': ha_low,
            'close': ha_close
        })

        # Copy volume if it exists
        if 'volume' in df.columns:
            ha_df['volume'] = df['volume'].copy()

        return ha_df

    except Exception as e:
        print(f"Error in Heikin-Ashi calculation: {e}")
        return pd.DataFrame()


# noinspection PyTypeChecker
def get_instrument_token(exchange: str, ticker: str) -> Optional[int]:
    """
    Get instrument token for a given ticker symbol and exchange.

    Args:
        exchange (str): Exchange code (e.g., 'NSE', 'BSE')
        ticker (str): Ticker symbol (e.g., 'RELIANCE', 'NIFTY 50')

    Returns:
        int: Instrument token if found, None otherwise
    """
    try:
        # Read the CSV file into a DataFrame
        instruments_df = pd.read_csv("src/Dependencies/tradeable_instruments.csv")

        # Convert ticker to uppercase and strip whitespace
        ticker_upper = ticker.upper().strip()

        # Try exact match on tradingsymbol and exchange
        exact_match = instruments_df[
            (instruments_df['tradingsymbol'].str.upper() == ticker_upper) &
            (instruments_df['exchange'].str.upper() == exchange.upper())
            ]

        if not exact_match.empty:
            return int(exact_match.iloc[0]['instrument_token'])

        # Try partial match if no exact match found
        partial_match = instruments_df[
            (instruments_df['tradingsymbol'].str.upper().str.contains(ticker_upper)) &
            (instruments_df['exchange'].str.upper() == exchange.upper())
            ]

        if not partial_match.empty:
            matched = partial_match.iloc[0]
            print(f"Found match for {ticker}: {matched['tradingsymbol']}")
            return int(matched['instrument_token'])

        print(f"❌ No instrument found for {ticker} on {exchange}")
        return None

    except FileNotFoundError:
        print("❌ Instrument list file not found at 'Dependencies/tradeable_instruments.csv'")
        return None
    except Exception as e:
        print(f"❌ Error getting token for {ticker}: {str(e)}")
        return None

def get_futures_list(underlying_name, instrument_file):
    """
    Get a list of all available futures contracts for the given underlying name.

    Args:
        underlying_name (str): Name of the underlying (e.g., 'NIFTY', 'BANK NIFTY')

    Returns:
        list: List of dictionaries containing futures contract details,
              or None if error occurs
    """
    try:
        # Convert to uppercase for case-insensitive comparison
        underlying_upper = underlying_name.upper()
        
        # Filter for futures contracts of the given underlying
        # .query() or boolean indexing both work, but boolean indexing is standard
        futures = instrument_file[
            (instrument_file["instrument_type"] == "FUT") & 
            (instrument_file["name"].str.upper() == underlying_upper)
        ].copy()
        
        if futures.empty:
            print(f"❌ No futures contracts found for {underlying_name}")
            return None
        
        # Select and cast the required fields
        # Using .astype() to handle the type conversions
        futures = futures[[
            "instrument_token", 
            "tradingsymbol", 
            "expiry", 
            "lot_size", 
            "tick_size", 
            "exchange"
        ]].astype({
            "instrument_token": "int64",
            "lot_size": "int64",
            "tick_size": "float64"
        })
        
        # Convert to list of dictionaries
        # 'records' orientation gives you the list of dicts [{col: val}, ...]
        return futures.to_dict(orient='records')

    except Exception as e:
        print(f"❌ An error occurred: {str(e)}")
        return None

def finding_strike_delta_based(underlying_name, instrument_file, initial_strike, contract, underlying_price, kite, delta_):
    interestRate = 5.27         # 91D T-Bill yield govt. bond
    options = instrument_file[
        (instrument_file['name'] == underlying_name) &
        (instrument_file['instrument_type'] == contract)
    ]

    pd_dates = pd.to_datetime(options['expiry'].to_list()).unique()
    now = pd.Timestamp.today()
    next_month_dt = now + pd.DateOffset(months=1)

    # Current month expiry
    cur_mask = (pd_dates.year == now.year) & (pd_dates.month == now.month)
    cur_month_expiry = pd_dates[cur_mask].max() if cur_mask.any() else None

    # Determine selected expiry based on days remaining
    if cur_month_expiry and (cur_month_expiry - now).days < 7:
        # Use next month
        next_mask = (pd_dates.year == next_month_dt.year) & (pd_dates.month == next_month_dt.month)
        selected_expiry = pd_dates[next_mask].max().date().isoformat() if next_mask.any() else None
    else:
        # Use current month
        selected_expiry = cur_month_expiry.date().isoformat() if cur_month_expiry else None

    days_to_expire = (cur_month_expiry - now).days + 1 # type: ignore

    if contract == "CE":
        strike_range = range(initial_strike, initial_strike + (100 * 15), 100)
    else:
        strike_range = range(initial_strike, initial_strike - (100 * 15), -100)
    tokens = []
    strike_map = {}
    
    for strike in strike_range:
        strike_options = instrument_file[
            (instrument_file['expiry'] == selected_expiry) &
            (instrument_file['name'] == underlying_name) &
            (instrument_file['strike'] == strike) &
            (instrument_file['instrument_type'] == contract)
        ].reset_index(drop=True)
        if not strike_options.empty:
            token = str(strike_options['instrument_token'][0])
            tokens.append(token)
            strike_map[token] = (strike, strike_options['tradingsymbol'][0], strike_options['lot_size'][0])

    ltp_data = kite.ltp(tokens)

    for token, strike in strike_map.items():
        strike_ltp = ltp_data[token]['last_price']
        trading_symbol = strike[1]
        lot_size = int(strike[2])
        bs_params = [underlying_price, strike[0], interestRate, days_to_expire]
        c = None
        IV = None
        if contract == 'CE':
            c = mibian.BS(bs_params, callPrice=strike_ltp)
        elif contract == 'PE':
            c = mibian.BS(bs_params, putPrice=strike_ltp)
        if c is not None:
            IV = c.impliedVolatility
        delta = mibian.BS(bs_params, volatility=IV)
        if contract == 'CE':
            delta = delta.callDelta * 100
        elif contract == 'PE':
            delta = delta.putDelta * 100
        delta = abs(delta)
        if delta < delta_:
            return token, trading_symbol, lot_size, strike_ltp

def camarilla_pivot_calculation(data):
    """
    data: feed data in dictionary key: value pairs
    example; { 'high': int/float, 'low': int/float, 'close': int/float }
    """
    daily_high       = data['high']
    daily_low        = data['low']
    daily_close      = data['close']

    range = round(daily_high - daily_low, 2)

    # calculation of 'central pivot range' (CPR)
    pivot            = round((daily_high + daily_low + daily_close) / 3, 2)
    bottom_central   = round((daily_high + daily_low) / 2, 2)
    top_central      = round((pivot - bottom_central) + pivot, 2)

    # calculation of camarilla pivot points
    resistance_1     = round(daily_close + range * 1.1 / 12, 2)
    resistance_2     = round(daily_close + range * 1.1 / 6, 2)
    resistance_3     = round(daily_close + range * 1.1 / 4, 2)
    resistance_4     = round(daily_close + range * 1.1 / 2, 2)
    resistance_5     = round((daily_high / daily_low) * daily_close, 2)

    support_1        = round(daily_close - range * 1.1 / 12, 2)
    support_2        = round(daily_close - range * 1.1 / 6, 2)
    support_3        = round(daily_close - range * 1.1 / 4, 2)
    support_4        = round(daily_close - range * 1.1 / 2, 2)
    support_5        = round(daily_close - (resistance_5 - daily_close), 2)
    
    return {
        "pivot": pivot, "bottom_central": bottom_central, "top_central": top_central, "R1": resistance_1, "R2": resistance_2, "R3": resistance_3, "R4": resistance_4, "R5": resistance_5, "S1": support_1, "S2": support_2, "S3": support_3, "S4": support_4, "S5": support_5
    }

def cpr_metrics(pivot, TC, BC):
    """
    Summary Table for Pivot Range Histogram Interpretation:

    | Histogram Value | Market Forecast and Conviction                            |
    | :-------------- | :-------------------------------------------------------- |
    | **Below 0.25**  | **Highly likely** to be an explosive **Trending Day**.    |
    | **0.25 - 0.50** | **Likely** to be a **Trending Day**.                      |
    | **Exactly 0.50**| **Midline** / Neutral point between trend and range.      |
    | **0.50 - 0.75** | **Likely** to be a **Sideways** or **Trading Range Day**. |
    | **Above 0.75**  | **Highly likely** to be a quiet or **Sideways Day**.      |

    The **Pivot Range Histogram** mathematically measures the width of the central pivot range to forecast whether the market will be trending or sideways. 
    According to the sources, any reading **below the midline of 0.5** indicates a trending type of day. 
    Conversely, any reading **above 0.5** indicates a sideways or trading range session. 
    The mathematical formula used to derive this metric is **((TC - BC) / PP) * 100**. 
    An unusually tight pivot range indicates the prior day was a consolidation, which often leads to **breakout or trending behavior** in the upcoming session. 
    In contrast, an abnormally wide range suggests the market experienced a large move previously and is now likely to experience **low volatility or whipsaw activity**. 
    This analysis allows a trader to adjust their plan, such as switching between **trailing profit stops** for trending days or **fixed profit targets** for range-bound days.
    """
    actual_tc = max(TC, BC)
    actual_bc = min(TC, BC)

    pivot_width_ratio = abs(actual_tc - actual_bc) / pivot

    return round(pivot_width_ratio * 100, 2)

def two_day_relationship(t_high, t_low, y_high, y_low, index):
    if t_low > y_high:
        return "Bullish: High conviction"
    elif t_high > y_high and t_low < y_high:
        return "Moderately Bullish: Strength is wavering"
    elif t_high < y_low:
        return "Bearish: High conviction"
    elif t_low < y_low and t_high > y_low:
        return "Moderately Bearish: Sellers losing power"
    elif t_high == y_high and t_low == y_low:
        return "Neutral: Breakout likely on third day"
    elif t_high > y_high and t_low < y_low:
        return "Sideways: Trading range/Whipsaw"
    elif t_high < y_high and t_low > y_low:
        return "Breakout: Most explosive potential"
