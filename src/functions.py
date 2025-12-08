from pathlib import Path
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs
from typing import cast, Dict, Any

import pandas as pd
import polars as pl
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
    send_telegram_message(bot_token, chat_id, "📥 Downloading instrument data...")
    
    exchanges = ['NSE', 'NFO', 'BSE', 'BFO', 'MCX']
    all_instruments = []
    
    # Fetch instruments for each exchange
    for exchange in exchanges:
        try:
            instruments = kite.instruments(exchange=exchange)
            all_instruments.extend(instruments)
            send_telegram_message(bot_token, chat_id, 
                                f"✓ Fetched {len(instruments)} instruments from {exchange}")
        except Exception as e:
            error_msg = f"⚠ Could not fetch instruments for {exchange}: {str(e)}"
            send_telegram_message(bot_token, chat_id, error_msg)
    
    # Save instruments data if any were fetched
    if all_instruments:
        df = pd.DataFrame(all_instruments)
        df.to_csv(deps_dir / "tradeable_instruments.csv", index=False)
        success_msg = f"✅ Successfully saved {len(df)} instruments to tradeable_instruments.csv"
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
        instruments_df = pd.read_csv("Dependencies/tradeable_instruments.csv")

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

def get_futures_list(underlying_name):
    """
    Get a list of all available futures contracts for the given underlying name.

    Args:
        underlying_name (str): Name of the underlying (e.g., 'NIFTY', 'BANK NIFTY')

    Returns:
        list: List of dictionaries containing futures contract details,
              or None if error occurs
    """
    try:
        # Read the instrument file using Polars
        try:
            df = pl.scan_csv('Dependencies/tradeable_instruments.csv')
        except Exception as e:
            print(f"❌ Error reading instrument file: {str(e)}")
            return None
        
        # Convert to uppercase for case-insensitive comparison
        underlying_upper = underlying_name.upper()
        
        # Filter for futures contracts of the given underlying
        futures = (df
            .filter(
                (pl.col("instrument_type") == "FUT") &
                (pl.col("name").str.to_uppercase() == underlying_upper)
            )
            .collect()
        )
        
        if futures.is_empty():
            print(f"❌ No futures contracts found for {underlying_name}")
            return None
        
        # Select and format the required fields
        futures = futures.select([
            pl.col("instrument_token").cast(pl.Int64),
            "tradingsymbol",
            "expiry",
            pl.col("lot_size").cast(pl.Int64),
            pl.col("tick_size").cast(pl.Float64),
            "exchange"
        ])
        
        # Convert to list of dictionaries
        return futures.to_dicts()
        
    except FileNotFoundError:
        print("❌ Instrument list file not found at 'Dependencies/tradeable_instruments.csv'")
        return None
    except Exception as e:
        print(f"❌ Error fetching futures list: {str(e)}")
        import traceback
        traceback.print_exc()
        return None