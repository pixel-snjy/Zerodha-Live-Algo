import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pandas_ta as pta
from kiteconnect import KiteConnect

import functions

##### Create Dependencies directory if it doesn't exist #####
deps_dir = Path("src/Dependencies")
deps_dir.mkdir(exist_ok=True)

#-----------------------------------------------------------------------------------------------------------------------

##### Loading key credentials #####
with open("src/do_not_delete/api-core.json", "r") as creds:
    data = json.load(creds)
api_key = data["zerodha_api_key"]
api_secret = data["zerodha_api_secret"]
telegram_bot_token = data["telegram_bot_token"]
personal_telegram_id = data["personal_telegram_id"]
broadcast_telegram_id = data["group_telegram_id"]
#-----------------------------------------------------------------------------------------------------------------------

##### Login flow #####
try:
    with open(deps_dir / "access_token.txt", "r") as file:
        access_token = file.read()
    kite = KiteConnect(api_key)
    kite.set_access_token(access_token)
    kite.margins()
except Exception as e:
    print(f"An unexpected error occurred: {e}")
    functions.login(api_key, api_secret, telegram_bot_token, personal_telegram_id)
    with open(deps_dir / "access_token.txt", "r") as file:
        access_token = file.read()
    kite = KiteConnect(api_key)
    kite.set_access_token(access_token)
#-----------------------------------------------------------------------------------------------------------------------

##### Static variables #####
last_run_minute = None
transaction_type = None

testing = 0 # 1 means yes && 0 means no

while testing == 0:
    # logic to skip the order flow beyond market hours
    if datetime.now().time() <= datetime.time(datetime.strptime("09:15", "%H:%M")):
        print("Market is closed")
        # time.sleep(60)
        continue

    # Logic to change order from regular to amo
    current_date = datetime.now().date()
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
    if current_minute % 5 == 0 and last_run_minute != current_minute:
    # if True:
        # print("Running logic")
        # for_15m_data = current_date - timedelta(days=28)
        for_5m_data = current_date - timedelta(days=10)

        ##### Fetch Instrument #####
        # chart_15m = kite.historical_data(instrument_token=256265, interval="15minute", from_date=for_15m_data,
        #                                  to_date=current_date)
        chart_5m = kite.historical_data(instrument_token=256265, interval="5minute", from_date=for_5m_data,
                                        to_date=current_date)

        # chart = kite
        fut_df = pd.DataFrame(chart_5m)
        # opt_df = pd.DataFrame(chart_15m)
        ha_fut_df = functions.convert_heikin_ashi(fut_df).round(2)
        # -----------------------------------------------------------------------------------------------------------------------

        ##### Strategy 1 ==>> Double SuperTrend for Directional Trade #####
        st1_ha = pta.supertrend(
            high=ha_fut_df['high'], low=ha_fut_df['low'], close=ha_fut_df['close'], length=11, multiplier=1
        ).round(2)
        st2_ha = pta.supertrend(
            high=ha_fut_df['high'], low=ha_fut_df['low'], close=ha_fut_df['close'], length=18, multiplier=2
        ).round(2)
        st1_ha_direction = st1_ha.iloc[-2, 1]
        stop_loss = st1_ha.iloc[-2, 0]
        st2_ha_direction = st2_ha.iloc[-2, 1]

        # Calling Futures
        futures = functions.get_futures_list('NIFTY')

        # Near Future & it's LTP fetched
        near_futures = futures[0]['tradingsymbol']
        near_futures_ltp = kite.ltp(futures[0]['instrument_token'])[str(futures[0]['instrument_token'])]['last_price']

        # Next Future & it's LTP fetched
        next_futures = futures[1]['tradingsymbol']
        next_futures_ltp = kite.ltp(futures[1]['instrument_token'])[str(futures[1]['instrument_token'])]['last_price']

        # Collecting data for Long Condition
        bc1 = st1_ha_direction == 1
        bc2 = st2_ha_direction == 1
        bc3 = transaction_type is None

        # Collecting data for Short Condition
        sc1 = st1_ha_direction == -1
        sc2 = st2_ha_direction == -1
        sc3 = transaction_type is None

        # Checking Long Condition
        if bc1 and bc2 and bc3:
            transaction_type       = "BUY"
            long_stop_loss_trigger = stop_loss
            risk_amount = near_futures_ltp - stop_loss
            long_target_trigger = round(near_futures_ltp + (risk_amount.round(2) * 3), 1)  # 1:3 risk-reward ratio

            # Sending Telegram update
            telegram_message = (
                "<b>🚨 Still in experimental stage, do not trade</b>\n\n"
                f"{transaction_type} | {near_futures} @ {near_futures_ltp}\n"
                f"with an Stop-loss @ {long_stop_loss_trigger}\n"
                f"with an Target @ {long_target_trigger}"
            )
            functions.send_telegram_message(telegram_bot_token, personal_telegram_id, telegram_message)

            # Placing Order
            order_id = kite.place_order(
                variety            = order_variety,
                exchange           = "NFO",
                tradingsymbol      = near_futures,
                transaction_type   = transaction_type,
                quantity           = int(futures[0]['lot_size']),
                product            = "NRML",
                order_type         = "LIMIT",
                price              = near_futures_ltp
            )

            # Placing GTT OCO
            long_gtt_order_id  = kite.place_gtt(
                trigger_type   = 'two-leg',
                tradingsymbol  = near_futures,
                exchange       = 'NFO',
                trigger_values = [
                    long_stop_loss_trigger,
                    long_target_trigger
                ],
                last_price     = near_futures_ltp,
                orders         = [
                    # Stop loss order
                    {
                        "transaction_type": 'SELL',
                        "quantity": int(futures[0]['lot_size']),
                        "price": long_stop_loss_trigger,  # 0 for market order
                        "order_type": "LIMIT",
                        "product": "NRML"
                    },
                    # Target order
                    {
                        "transaction_type": 'SELL',
                        "quantity": int(futures[0]['lot_size']),
                        "price": long_target_trigger,  # 0 for market order
                        "order_type": "LIMIT",
                        "product": "NRML"
                    }
                ]
            )

        # Checking Short Condition
        elif sc1 and sc2 and sc3:
            transaction_type        = "SELL"
            short_stop_loss_trigger = stop_loss
            risk_amount = near_futures_ltp - stop_loss
            short_target_trigger = round(near_futures_ltp - (risk_amount * 3), 2)  # 1:3 risk-reward ratio

            # Sending Telegram update
            telegram_message = (
                "<b>🚨 Still in experimental stage, do not trade</b>\n\n"
                f"{transaction_type} | {near_futures} @ {near_futures_ltp}\n"
                f"with an Stop-loss @ {short_stop_loss_trigger}\n"
                f"with an Target @ {short_target_trigger}"
            )
            functions.send_telegram_message(telegram_bot_token, personal_telegram_id, telegram_message)

            # Place Order
            order_id = kite.place_order(
                variety              = order_variety,
                exchange             = "NFO",
                tradingsymbol        = near_futures,
                transaction_type     = transaction_type,
                quantity             = futures[0]['lot_size'],
                product              = "NRML",
                order_type           = "LIMIT",
                price                = near_futures_ltp
            )

            # Placing GTT OCO
            short_gtt_order_id = kite.place_gtt(
                trigger_type   = 'two-leg',
                tradingsymbol  = near_futures,
                exchange       = 'NFO',
                trigger_values = [
                    short_stop_loss_trigger,
                    short_target_trigger
                ],
                last_price     = near_futures_ltp,
                orders         = [
                    # Stop loss order
                    {
                        "transaction_type": 'BUY',
                        "quantity": int(futures[0]['lot_size']),
                        "price": short_stop_loss_trigger,  # 0 for market order
                        "order_type": "LIMIT",
                        "product": "NRML"
                    },
                    # Target order
                    {
                        "transaction_type": 'BUY',
                        "quantity": int(futures[0]['lot_size']),
                        "price": short_target_trigger,  # 0 for market order
                        "order_type": "LIMIT",
                        "product": "NRML"
                    }
                ]
            )

        # Check if any GTT order was triggered and reset transaction_type if needed
        if transaction_type is not None:
            try:
                # Get all active GTTs
                active_gtts = kite.get_gtts()
                
                # Check if our GTT is still active
                # noinspection PyUnboundLocalVariable
                current_gtt_id = long_gtt_order_id['trigger_id'] if transaction_type == 'BUY' else short_gtt_order_id['trigger_id']
                gtt_active = any(gtt['id'] == current_gtt_id for gtt in active_gtts)
                
                if not gtt_active:
                    # GTT was triggered, reset transaction_type
                    print(f"GTT order {current_gtt_id} was triggered. Resetting transaction_type.")
                    transaction_type = None
                    
            except Exception as e:
                print(f"Error checking GTT status: {e}")
                # In case of any error, we'll check again in the next iteration
                pass



    # print("Sleeping for 15 seconds")
    time.sleep(15)
    last_run_minute = current_minute

    # Checking the overall market close time
    if datetime.now().time() >= datetime.time(datetime.strptime("15:30", "%H:%M")):
        # print("Market is closed")
        break

