import json
import time
from datetime import datetime, timedelta
from pathlib import Path
import pyotp
import os

import pandas as pd
import pandas_ta_classic as pta
from kiteconnect import KiteConnect

import serverside_functions

# Create Dependencies directory if it doesn't exist 
deps_dir = Path("src/Dependencies")
deps_dir.mkdir(exist_ok=True)

#-----------------------------------------------------------------------------------------------------------------------

# Loading key credentials 
with open("src/do_not_delete/api-core.json", "r") as creds:
    data = json.load(creds)
api_key = data["zerodha_api_key"]
api_secret = data["zerodha_api_secret"]
telegram_bot_token = data["telegram_bot_token"]
personal_telegram_id = data["personal_telegram_id"]
broadcast_telegram_id = data["group_telegram_id"]
totp_secret_key = data['zerodha_totp_secret_key']

# interestRate = 5.27 # 91D T-Bill
#-----------------------------------------------------------------------------------------------------------------------

# Login flow

totp = pyotp.TOTP(totp_secret_key)
otp = totp.now()

try:
    with open(deps_dir / "access_token.txt", "r") as file:
        access_token = file.read()
    kite = KiteConnect(api_key)
    kite.set_access_token(access_token)
    kite.margins()
except Exception as e:
    print(f"An unexpected error occurred: {e}")
    serverside_functions.login(api_key, api_secret, telegram_bot_token, personal_telegram_id)
    with open(deps_dir / "access_token.txt", "r") as file:
        access_token = file.read()
    kite = KiteConnect(api_key)
    kite.set_access_token(access_token)
#-----------------------------------------------------------------------------------------------------------------------

# watchlist
watchlist = {
    'NIFTY': 256265,
    'SENSEX': 265,
    'NIFTYBANK': 260105
}

# loading instrument file 
instrument_file = pd.read_csv(deps_dir / 'tradeable_instruments.csv')

# Static variables 
last_run_minute          = None
getting                  = None
current_date             = datetime.now().date()
yesterday_date           = current_date - timedelta(days=1)
the_day_before_yesterday = current_date - timedelta(days=2)
if datetime.now().time() >= datetime.time(datetime.strptime("15:35", "%H:%M")):
    current_date += timedelta(days=1)
    yesterday_date += timedelta(days=1)
    the_day_before_yesterday += timedelta(days=1)
if yesterday_date.weekday() == 6:
    yesterday_date  -= timedelta(days=2)
elif yesterday_date.weekday() == 5:
    yesterday_date  -= timedelta(days=1)
if the_day_before_yesterday.weekday() == 6:
    the_day_before_yesterday -= timedelta(days=2)
elif the_day_before_yesterday.weekday() == 5:
    the_day_before_yesterday -= timedelta(days=1)

"""
calculation of yesterday pivots in futures if available.
if today is expiry then tomorrow, calculate spot pivot.
"""
pivot_df = {}

next_session_cpr_metric_df = {}
two_day_relationship_df = {}

for key, value in watchlist.items():
    spot_data = kite.historical_data(instrument_token=value, interval='day', from_date=the_day_before_yesterday, to_date=yesterday_date)
    for i in range(len(spot_data)):
        previous_day_high = spot_data[i]['high']
        previous_day_low = spot_data[i]['low']
        previous_day_close = spot_data[i]['close']
        daily_pivots = serverside_functions.camarilla_pivot_calculation(data=spot_data[i])
        if key not in pivot_df:
            pivot_df[key] = {}
        pivot_df[key][i] = daily_pivots

for key in pivot_df:
    next_session_cpr_metric = serverside_functions.cpr_metrics(pivot=pivot_df[key][1]['pivot'], TC=pivot_df[key][1]['top_central'], BC=pivot_df[key][1]['bottom_central'])

    logic_flow_from_two_day_relationship = serverside_functions.two_day_relationship(t_high=pivot_df[key][1]['R3'], t_low=pivot_df[key][1]['S3'], y_high=pivot_df[key][0]['R3'], y_low=pivot_df[key][0]['S3'], index=key)

    if key not in next_session_cpr_metric_df and key not in two_day_relationship_df:
        next_session_cpr_metric_df[key] = {}
        two_day_relationship_df[key] = {}
    next_session_cpr_metric_df[key] = next_session_cpr_metric
    two_day_relationship_df[key] = logic_flow_from_two_day_relationship

# 1 means yes && 0 means no
testing = 1
punch_order = 0

# logic to pause the script till 0930Hrs or desired time.
now = datetime.now()
now_time = now.time()
target_time = datetime.time(datetime.strptime("09:30", "%H:%M"))
if testing == 0:
    if now_time < target_time:
        target_dt = datetime.combine(now.date(), target_time)
        seconds_to_sleep = int((target_dt - now).total_seconds())
        if seconds_to_sleep > 0:
            time.sleep(seconds_to_sleep)
        now_time = datetime.now().time()

while True:

    # logic to tell user that market is open & logic starting to execute
    now_time = datetime.now().time()
    if now_time < target_time:
        serverside_functions.send_telegram_message(
            bot_token= telegram_bot_token,
            chat_id= personal_telegram_id,
            text= "Market Open & Logic started to execute"
        )

    # logic to skip the order flow beyond market hours
    if testing == 0:
        if now_time >= datetime.time(datetime.strptime("15:30", "%H:%M")):
            # Send alert to Telegram
            serverside_functions.send_telegram_message(
                bot_token = telegram_bot_token,
                chat_id   = personal_telegram_id,
                text      = "Market is closed"
                )
            try:
                os.remove(f"{deps_dir}/access_token.txt")
            except Exception as e:
                serverside_functions.send_telegram_message(
                bot_token = telegram_bot_token,
                chat_id   = personal_telegram_id,
                text      = f"Exception {e} raised while deleting access_token & instrument_file"
                )
            time.sleep(1)
            break

    # Logic to change order from regular to amo
    # current_date = datetime.now().date()
    equity_trading_hours = (
            datetime.time(
            datetime.strptime("09:15", "%H:%M")) <= datetime.now().time() <= datetime.time(
            datetime.strptime("15:30", "%H:%M"))
    )
    if not equity_trading_hours:
        order_variety = 'amo'
    else:
        order_variety = 'regular'

    current_minute = datetime.now().minute
    # if current_minute % 15 == 0 and last_run_minute != current_minute:
    if True:
        print("Running logic")
        for_15m_data = current_date - timedelta(days=28)
        # for_5m_data = current_date - timedelta(days=10)

        # Fetch Instrument 
        nifty_index = "256265"
        nifty_futures = ""
        # chart_15m = kite.historical_data(instrument_token=256265, interval="15minute", from_date=for_15m_data,
        #                                  to_date=current_date)
        chart_5m = kite.historical_data(instrument_token=nifty_index, interval="15minute", from_date=for_15m_data,
                                        to_date=current_date)

        # chart = kite
        chart_df = pd.DataFrame(chart_5m)
        # opt_df = pd.DataFrame(chart_15m)
        ha_chart_df = serverside_functions.convert_heikin_ashi(chart_df).round(2)
        # -----------------------------------------------------------------------------------------------------------------------

        # Strategy 1 ==>> Double SuperTrend for Directional Trade 
        st1_ha = pta.supertrend(
            high=ha_chart_df['high'], low=ha_chart_df['low'], close=ha_chart_df['close'], length=11, multiplier=1
        ).round(2)
        st2_ha = pta.supertrend(
            high=ha_chart_df['high'], low=ha_chart_df['low'], close=ha_chart_df['close'], length=18, multiplier=2
        ).round(2)
        st1_ha_direction = st1_ha.iloc[-1, 1].item()
        stop_loss = st1_ha.iloc[-1, 0].item()
        st2_ha_direction = st2_ha.iloc[-1, 1].item()
        prev_st2_ha_direction = st2_ha.iloc[-2, 1].item()
        selling_strike = int(round(stop_loss, -2))

        # Collecting data for Long Condition
        bc1 = st1_ha_direction == 1
        bc2 = st2_ha_direction == 1
        bc3 = getting is None
        bc4 = prev_st2_ha_direction == -1

        # Collecting data for Short Condition
        sc1 = st1_ha_direction == -1
        sc2 = st2_ha_direction == -1
        sc3 = getting is None
        sc4 = prev_st2_ha_direction == 1

        # Checking Long Condition 
        if bc1 and bc2 and bc3 and bc4:
        # if True:
            contract                         = 'PE'
            getting                          = "long"
            underlying_ltp                   = kite.ltp(nifty_index)
            underlying_ltp                   = underlying_ltp[nifty_index]['last_price'] # type: ignore

            # Executing Hedge first
            pe_opt_hedge_id = serverside_functions.finding_strike_delta_based(
                underlying_name              = 'NIFTY',
                instrument_file              = instrument_file,
                initial_strike               = selling_strike,
                contract                     = contract,
                underlying_price             = underlying_ltp,
                kite                         = kite,
                delta_                       = 10
            )

            hedgig_id                        = pe_opt_hedge_id[0] # type: ignore
            hedging_strike_trading_symbol    = pe_opt_hedge_id[1] # type: ignore
            hedging_strike_lot_size          = pe_opt_hedge_id[2] # type: ignore
            hedging_strike_price             = pe_opt_hedge_id[3] # type: ignore

            # pe_hedge_order_id = None
            if punch_order == 1:
                # Placing Order
                pe_hedge_order_id = kite.place_order(
                    variety            = order_variety,
                    exchange           = "NFO",
                    tradingsymbol      = hedging_strike_trading_symbol,
                    transaction_type   = "BUY",
                    quantity           = hedging_strike_lot_size,
                    product            = "NRML",
                    order_type         = "LIMIT",
                    price              = hedging_strike_price
                )

                order_status = None
                while order_status != 'COMPLETE':
                    orders = kite.orders()
                    # for order in orders:
                    for order in range(len(orders)):
                        order_id = orders[order]['order_id']
                        if order_id == pe_hedge_order_id:
                            order_status = orders[order]['status']
                            time.sleep(1)

            # executing sell order next
            pe_opt_sell_id = serverside_functions.finding_strike_delta_based(
                underlying_name              = 'NIFTY',
                instrument_file              = instrument_file,
                initial_strike               = selling_strike,
                contract                     = contract,
                underlying_price             = underlying_ltp,
                kite                         = kite,
                delta_                       = 35
            )

            selling_id                       = pe_opt_sell_id[0] # type: ignore
            selling_strike_trading_symbol    = pe_opt_sell_id[1] # type: ignore
            selling_strike_lot_size          = pe_opt_sell_id[2] # type: ignore
            selling_strike_price             = pe_opt_sell_id[3] # type: ignore

            # pe_sell_order_id = None
            if punch_order == 1:
                # Placing Order
                pe_sell_order_id = kite.place_order(
                    variety            = order_variety,
                    exchange           = "NFO",
                    tradingsymbol      = selling_strike_trading_symbol,
                    transaction_type   = "SELL",
                    quantity           = selling_strike_lot_size,
                    product            = "NRML",
                    order_type         = "LIMIT",
                    price              = selling_strike_price
                )

                order_status = None
                while order_status != 'COMPLETE':
                    orders = kite.orders()
                    # for order in orders:
                    for order in range(len(orders)):
                        order_id = orders[order]['order_id']
                        if order_id == pe_sell_order_id:
                            order_status = orders[order]['status']
                            time.sleep(1)
            
            # sending order update to telegram
            telegram_message = (
                "<b>🚨 Still in experimental stage, do not trade</b>\n\n"
                f"Getting {getting}\n"
                f"Selling {selling_strike_trading_symbol} @ <b>{selling_strike_price}</b>\n"
                f"with\n"
                f"Hedge {hedging_strike_trading_symbol} @ <b>{hedging_strike_price}</b>\n"
            )
            serverside_functions.send_telegram_message(telegram_bot_token, personal_telegram_id, telegram_message)

        
        # Checking Short Condition
        elif sc1 and sc2 and sc3 and sc4:
        # if True:
            contract                         = 'CE'
            getting                          = "short"
            underlying_ltp                   = kite.ltp(nifty_index)
            underlying_ltp                   = underlying_ltp[nifty_index]['last_price'] # type: ignore

            # Executing Hedge first
            ce_opt_hedge_id = serverside_functions.finding_strike_delta_based(
                underlying_name              = 'NIFTY',
                instrument_file              = instrument_file,
                initial_strike               = selling_strike,
                contract                     = contract,
                underlying_price             = underlying_ltp,
                kite                         = kite,
                delta_                       = 10
            )

            hedgig_id                        = ce_opt_hedge_id[0] # type: ignore
            hedging_strike_trading_symbol    = ce_opt_hedge_id[1] # type: ignore
            hedging_strike_lot_size          = ce_opt_hedge_id[2] # type: ignore
            hedging_strike_price             = ce_opt_hedge_id[3] # type: ignore

            # ce_hedge_order_id = None
            if punch_order == 1:
                # Placing Order
                ce_hedge_order_id = kite.place_order(
                    variety            = order_variety,
                    exchange           = "NFO",
                    tradingsymbol      = hedging_strike_trading_symbol,
                    transaction_type   = "BUY",
                    quantity           = hedging_strike_lot_size,
                    product            = "NRML",
                    order_type         = "LIMIT",
                    price              = hedging_strike_price
                )

                order_status = None
                while order_status != 'COMPLETE':
                    orders = kite.orders()
                    # for order in orders:
                    for order in range(len(orders)):
                        order_id = orders[order]['order_id']
                        if order_id == ce_hedge_order_id:
                            order_status = orders[order]['status']
                            time.sleep(1)

            # executing order next
            ce_opt_sell_id = serverside_functions.finding_strike_delta_based(
                underlying_name              = 'NIFTY',
                instrument_file              = instrument_file,
                initial_strike               = selling_strike,
                contract                     = contract,
                underlying_price             = underlying_ltp,
                kite                         = kite,
                delta_                       = 35
            )

            selling_id                       = ce_opt_sell_id[0] # type: ignore
            selling_strike_trading_symbol    = ce_opt_sell_id[1] # type: ignore
            selling_strike_lot_size          = ce_opt_sell_id[2] # type: ignore
            selling_strike_price             = ce_opt_sell_id[3] # type: ignore

            if punch_order == 1:
                # Placing Order
                ce_sell_order_id = kite.place_order(
                    variety            = order_variety,
                    exchange           = "NFO",
                    tradingsymbol      = selling_strike_trading_symbol,
                    transaction_type   = "SELL",
                    quantity           = selling_strike_lot_size,
                    product            = "NRML",
                    order_type         = "LIMIT",
                    price              = selling_strike_price
                )

                order_status = None
                while order_status != 'COMPLETE':
                    orders = kite.orders()
                    # for order in orders:
                    for order in range(len(orders)):
                        order_id = orders[order]['order_id']
                        if order_id == ce_sell_order_id:
                            order_status = orders[order]['status']
                            time.sleep(1)
            
            # send order update to telegram
            telegram_message = (
                "<b>🚨 Still in experimental stage, do not trade</b>\n\n"
                f"Getting {getting}\n"
                f"Selling {selling_strike_trading_symbol} @ <b>{selling_strike_price}</b>\n"
                f"with\n"
                f"Hedge {hedging_strike_trading_symbol} @ <b>{hedging_strike_price}</b>\n"
            )
            serverside_functions.send_telegram_message(telegram_bot_token, personal_telegram_id, telegram_message)

    elif current_minute % 30 == 0 and last_run_minute != current_minute:
        # send active update to telegram
        serverside_functions.send_telegram_message(
            bot_token     = telegram_bot_token,
            chat_id       = personal_telegram_id,
            text          = "Algorithm is still active")

    # sleeping for 15 seconds
    time.sleep(15)
    last_run_minute = current_minute

if datetime.now().time() >= datetime.time(datetime.strptime("15:35", "%H:%M")):
    current_date += timedelta(days=1)
    yesterday_date += timedelta(days=1)
    the_day_before_yesterday += timedelta(days=1)
