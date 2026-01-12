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
    # 'NIFTYBANK': 260105
}

# loading instrument file 
instrument_file = pd.read_csv(deps_dir / 'tradeable_instruments.csv')

# 1 means yes && 0 means no
testing = 0
punch_order = 0
strategy_one = 0
send_message = 1
marketClosed = True

# Static variables 
last_run_minute          = None
getting                  = None
is_market_live           = True
current_day              = datetime.now().date()
next_day                 = current_day + timedelta(days=1)
yesterday                = current_day - timedelta(days=1)
the_day_before_yesterday = current_day - timedelta(days=2)

# adjusting dates according to weekdays. when there is saturday or sunday days are adjusted accordingly.
if yesterday.weekday() == 6:
    yesterday  -= timedelta(days=2)
    the_day_before_yesterday -= timedelta(days=2)
elif yesterday.weekday() == 5:
    yesterday  -= timedelta(days=1)
    the_day_before_yesterday -= timedelta(days=1)
if the_day_before_yesterday.weekday() == 6:
    the_day_before_yesterday -= timedelta(days= 2)

"""
fetch daily hlc from two consecutive trading sessions.
based on them calculate CPR/Camarilla for next two consecutive day.
then based on CPR/Camarilla calculations do interpretation for next session.
"""

pivot_df = {}
nextSessionCPRHistograms = {}
twoDayRelationshipBasedOnH3andL3data = {}
twoDayRelationshipBasedOnCPRdata = {}

for key, value in watchlist.items():
    spot_data = kite.historical_data(instrument_token=value, interval='day', from_date=the_day_before_yesterday, to_date=yesterday)
    for i in range(len(spot_data)):
        previous_day_high = spot_data[i]['high']
        previous_day_low = spot_data[i]['low']
        previous_day_close = spot_data[i]['close']
        daily_pivots = serverside_functions.camarilla_pivot_calculation(data=spot_data[i])
        if key not in pivot_df:
            pivot_df[key] = {}
        pivot_df[key][i] = daily_pivots

for key in pivot_df:
    nextSessionCprBreadth = serverside_functions.cpr_metrics(pivot=pivot_df[key][1]['pivot'], TC=pivot_df[key][1]['top_central'], BC=pivot_df[key][1]['bottom_central'])

    logicFlowFromTwoDayRelationshipBasedOnH3AndL3 = serverside_functions.two_day_relationship(t_high=pivot_df[key][1]['R3'], t_low=pivot_df[key][1]['S3'], y_high=pivot_df[key][0]['R3'], y_low=pivot_df[key][0]['S3'], index=key)
    logicFlowFromTwoDayRelationshipBasedOnCPRdata = serverside_functions.two_day_relationship(t_high=pivot_df[key][1]['top_central'], t_low=pivot_df[key][1]['bottom_central'] , y_high=pivot_df[key][0]['top_central'], y_low=pivot_df[key][0]['bottom_central'], index=key)

    if key not in nextSessionCPRHistograms and key not in twoDayRelationshipBasedOnH3andL3data:
        nextSessionCPRHistograms[key] = {}
        twoDayRelationshipBasedOnH3andL3data[key] = {}
        twoDayRelationshipBasedOnCPRdata[key] = {}
    nextSessionCPRHistograms[key] = nextSessionCprBreadth
    twoDayRelationshipBasedOnH3andL3data[key] = logicFlowFromTwoDayRelationshipBasedOnH3AndL3
    twoDayRelationshipBasedOnCPRdata[key] = logicFlowFromTwoDayRelationshipBasedOnCPRdata

if send_message == 1:
    for key in pivot_df:
        early_message = (
            f"today <b>{key}</b> Spot information based on Camarilla Pivot:\n\n"
            f"pivot: {pivot_df[key][1]['pivot']}\n"
            f"bottom central: {pivot_df[key][1]['bottom_central']}\n"
            f"top central: {pivot_df[key][1]['top_central']}\n\n"
            f"resistance::\nR1:: {pivot_df[key][1]['R1']}\nR2:: {pivot_df[key][1]['R2']}\nR3:: {pivot_df[key][1]['R3']}\nR4:: {pivot_df[key][1]['R4']}\nR5:: {pivot_df[key][1]['R5']}\n"
            f"support::\nS1:: {pivot_df[key][1]['S1']}\nS2:: {pivot_df[key][1]['S2']}\nS3:: {pivot_df[key][1]['S3']}\nS4:: {pivot_df[key][1]['S4']}\nS5:: {pivot_df[key][1]['S5']}\n\n"
            f"<b>{nextSessionCPRHistograms[key]}</b>\n\n"
            f"two day value area relationship: using CPR\n{twoDayRelationshipBasedOnCPRdata[key]}\n\n"
            f"two day value area relationship: using L3 & H3\n{twoDayRelationshipBasedOnH3andL3data[key]}\n\n"
            # "⚠️ still in experimental stage\n"
        )

        serverside_functions.send_telegram_message(
            bot_token= telegram_bot_token,
            chat_id= personal_telegram_id,
            text= early_message
        )

    if current_day.weekday() == 4 or current_day.weekday() == 5 or current_day.weekday() == 6 or current_day.weekday() == 0 or current_day.weekday() == 1:
        select = 'NIFTY'
    elif current_day.weekday() == 2 or current_day.weekday() == 3:
        select = 'SENSEX'

    early_message = (
        f"today <b>{select}</b> Spot information based on Camarilla Pivot:\n\n"
        f"pivot: {pivot_df[select][1]['pivot']}\n"
        f"bottom central: {pivot_df[select][1]['bottom_central']}\n"
        f"top central: {pivot_df[select][1]['top_central']}\n\n"
        f"resistance::\nR1:: {pivot_df[select][1]['R1']}\nR2:: {pivot_df[select][1]['R2']}\nR3:: {pivot_df[select][1]['R3']}\nR4:: {pivot_df[select][1]['R4']}\nR5:: {pivot_df[select][1]['R5']}\n"
        f"support::\nS1:: {pivot_df[select][1]['S1']}\nS2:: {pivot_df[select][1]['S2']}\nS3:: {pivot_df[select][1]['S3']}\nS4:: {pivot_df[select][1]['S4']}\nS5:: {pivot_df[select][1]['S5']}\n\n"
        f"<b>{nextSessionCPRHistograms[select]}</b>\n\n"
        f"two day value area relationship: using CPR\n{twoDayRelationshipBasedOnCPRdata[key]}\n\n"
        f"two day value area relationship: using L3 & H3\n{twoDayRelationshipBasedOnH3andL3data[select]}\n\n"
        # "⚠️ still in experimental stage\n"
    )

    serverside_functions.send_telegram_message(
        bot_token= telegram_bot_token,
        chat_id= broadcast_telegram_id,
        text= early_message
    )

# logic to pause the script till 0930Hrs or desired time.
now = datetime.now()
nowTime = now.time()
targetTime = datetime.time(datetime.strptime("09:15", "%H:%M"))
if testing == 0:
    if nowTime < targetTime:
        targetDateTime = datetime.combine(now.date(), targetTime)
        secondsToSleep = int((targetDateTime - now).total_seconds())
        if secondsToSleep > 0:
            # print(f"pausing code till market open... for {secondsToSleep} seconds")
            time.sleep(secondsToSleep)

while is_market_live:
    # constant update need
    current_minute = datetime.now().minute # it's an integer value of a minute to operate under % comparison
    nowTime = datetime.now().time() # it's an actual datetime.time class
    current_day = datetime.now().date() # it's an actual datetime.date class

    if datetime.time(datetime.strptime("15:15", "%H:%M")) <= nowTime < datetime.time(datetime.strptime("15:30", "%H:%M")):
        # print(f"running a hypothesis analysis for next session... @ {nowTime}")
        for key, value in watchlist.items():
            spot_data = kite.historical_data(instrument_token=value, interval='day', from_date=yesterday, to_date=current_day)
            for i in range(len(spot_data)):
                previous_day_high = spot_data[i]['high']
                previous_day_low = spot_data[i]['low']
                previous_day_close = spot_data[i]['close']
                daily_pivots = serverside_functions.camarilla_pivot_calculation(data=spot_data[i])
                if key not in pivot_df:
                    pivot_df[key] = {}
                pivot_df[key][i] = daily_pivots

        for key in pivot_df:
            nextSessionCprBreadth = serverside_functions.cpr_metrics(pivot=pivot_df[key][1]['pivot'], TC=pivot_df[key][1]['top_central'], BC=pivot_df[key][1]['bottom_central'])

            logicFlowFromTwoDayRelationshipBasedOnH3AndL3 = serverside_functions.two_day_relationship(t_high=pivot_df[key][1]['R3'], t_low=pivot_df[key][1]['S3'], y_high=pivot_df[key][0]['R3'], y_low=pivot_df[key][0]['S3'], index=key)

            if key not in nextSessionCPRHistograms and key not in twoDayRelationshipBasedOnH3andL3data:
                nextSessionCPRHistograms[key] = {}
                twoDayRelationshipBasedOnH3andL3data[key] = {}
            nextSessionCPRHistograms[key] = nextSessionCprBreadth
            twoDayRelationshipBasedOnH3andL3data[key] = logicFlowFromTwoDayRelationshipBasedOnH3AndL3

        if send_message == 1:
            for key in pivot_df:
                early_message = (
                    f"tomorrow <b>{key}</b> Spot <b>hypothetical information</b> based on 3:15PM candle closing data:\n\n"
                    f"pivot: {pivot_df[key][1]['pivot']}\n"
                    f"bottom central: {pivot_df[key][1]['bottom_central']}\n"
                    f"top central: {pivot_df[key][1]['top_central']}\n\n"
                    f"resistance::\nR1:: {pivot_df[key][1]['R1']}\nR2:: {pivot_df[key][1]['R2']}\nR3:: {pivot_df[key][1]['R3']}\nR4:: {pivot_df[key][1]['R4']}\nR5:: {pivot_df[key][1]['R5']}\n"
                    f"support::\nS1:: {pivot_df[key][1]['S1']}\nS2:: {pivot_df[key][1]['S2']}\nS3:: {pivot_df[key][1]['S3']}\nS4:: {pivot_df[key][1]['S4']}\nS5:: {pivot_df[key][1]['S5']}\n\n"
                    f"<b>{nextSessionCPRHistograms[key]}</b>\n\n"
                    f"two day value area relationship: using CPR\n{twoDayRelationshipBasedOnCPRdata[key]}\n\n"
                    f"two day value area relationship: using L3 & H3\n{twoDayRelationshipBasedOnH3andL3data[key]}\n\n"
                    "⚠️ still in experimental stage\n"
                )

                serverside_functions.send_telegram_message(
                    bot_token= telegram_bot_token,
                    chat_id= broadcast_telegram_id,
                    text= early_message
                )

    # logic to tell user that market is open & logic starting to execute
    if nowTime == datetime.time(datetime.strptime("09:15", "%H:%M")):
        serverside_functions.send_telegram_message(
            bot_token= telegram_bot_token,
            chat_id= personal_telegram_id,
            text= "Market Open & Logic started to execute"
        )

    if testing == 0:
        # deleting access token after 12:30AM midnight, then stop the code from running in a loop.
        if nowTime >= datetime.time(datetime.strptime("00:30", "%H:%M")) and next_day == current_day:
            # print("stepped into this block to delete the access token and break the script")
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

        # sending message about market is closed.
        elif datetime.time(datetime.strptime("15:30", "%H:%M")) <= nowTime <= datetime.time(datetime.strptime("15:35", "%H:%M")) and marketClosed:
            # Send alert to Telegram
            serverside_functions.send_telegram_message(
                bot_token = telegram_bot_token,
                chat_id   = personal_telegram_id,
                text      = "Market is closed"
                )
            marketClosed = False
        
    # initial balance logic
    if datetime.time(datetime.strptime("10:15", "%H:%M")) <= nowTime < datetime.time(datetime.strptime("10:30", "%H:%M")):
    # if True:
        # print(f"checking the initial balance... @ {nowTime}")
        if current_day.weekday() == 4 or current_day.weekday() == 0 or current_day.weekday() == 1:
            token_id = watchlist['NIFTY']
        elif current_day.weekday() == 2 or current_day.weekday() == 3:
            token_id = watchlist['SENSEX']
        initial_balance_data = kite.historical_data(instrument_token=token_id, from_date=current_day, to_date=current_day, interval='60minute')
        # buyer ki toh banegi CE contract
        buyer = round(initial_balance_data[0]['low'], -2)
        # seller ki banegi PE contract
        seller = round(initial_balance_data[0]['high'], -2)
        

    # Logic to change order from regular to amo
    # current_date = datetime.now().date()
    equity_trading_hours = (
            datetime.time(
            datetime.strptime("09:15", "%H:%M")) <= nowTime <= datetime.time(
            datetime.strptime("15:30", "%H:%M"))
    )
    if not equity_trading_hours:
        order_variety = 'amo'
    else:
        order_variety = 'regular'

    if current_minute % 15 == 0 and last_run_minute != current_minute:
        # print(f"working... {last_run_minute} {current_minute}")
    # if False:
    # if True:
        # for_15m_data = current_day - timedelta(days=28)
        for_15m_data = current_day

        # Fetch Instrument 
        # watchlist['NIFTY'] = "256265"
        chart15m = kite.historical_data(instrument_token=watchlist['NIFTY'], interval="15minute", from_date=for_15m_data, to_date=current_day)

        # chart = kite
        chart_df = pd.DataFrame(chart15m)

        # fair value gap calculation
        fvg, fvg_high, fvg_low = serverside_functions.fair_value_gap(chart_df)
        if fvg == 'bullish fvg' or fvg == 'bearish fvg':
            serverside_functions.send_telegram_message(
                bot_token=telegram_bot_token,
                chat_id=broadcast_telegram_id,
                text=f"{fvg}\nHigh:: {fvg_high}\nLow:: {fvg_low}\n"
            )
        
        # candle stick pattern at camarilla levels, doji, hammer, engulfing

        
        # -----------------------------------------------------------------------------------------------------------------------

        # Strategy 1 ==>> Double SuperTrend for Directional Trade
        if strategy_one == 1:
            ha_chart_df = serverside_functions.convert_heikin_ashi(chart_df).round(2)
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
                underlying_ltp                   = kite.ltp(watchlist['NIFTY'])
                underlying_ltp                   = underlying_ltp[watchlist['NIFTY']]['last_price'] # type: ignore

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
                underlying_ltp                   = kite.ltp(watchlist['NIFTY'])
                underlying_ltp                   = underlying_ltp[watchlist['NIFTY']]['last_price'] # type: ignore

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

    if nowTime >= datetime.time(datetime.strptime("00", "%M")) and last_run_minute != current_minute:
        # send active update to telegram
        serverside_functions.send_telegram_message(
            bot_token     = telegram_bot_token,
            chat_id       = personal_telegram_id,
            text          = "Algorithm is still active"
        )

    last_run_minute = current_minute

    if nowTime >= datetime.time(datetime.strptime("00:15", "%H:%M")) and next_day == current_day:
        # print("stepped into this code block to send next day's trading bhaav.")
        if current_day.weekday() == 1:
            yesterday = current_day - timedelta(days=1)
            the_day_before_yesterday = current_day - timedelta(days=4)
        elif current_day.weekday() == 2:
            yesterday = current_day - timedelta(days=1)
            the_day_before_yesterday = current_day - timedelta(days=2)
        elif current_day.weekday() == 5:
            yesterday = current_day - timedelta(days=1)
            the_day_before_yesterday = current_day - timedelta(days=2)
    
        for key, value in watchlist.items():
            spot_data = kite.historical_data(instrument_token=value, interval='day', from_date=the_day_before_yesterday, to_date=yesterday)
            for i in range(len(spot_data)):
                previous_day_high = spot_data[i]['high']
                previous_day_low = spot_data[i]['low']
                previous_day_close = spot_data[i]['close']
                daily_pivots = serverside_functions.camarilla_pivot_calculation(data=spot_data[i])
                if key not in pivot_df:
                    pivot_df[key] = {}
                pivot_df[key][i] = daily_pivots

        for key in pivot_df:
            nextSessionCprBreadth = serverside_functions.cpr_metrics(pivot=pivot_df[key][1]['pivot'], TC=pivot_df[key][1]['top_central'], BC=pivot_df[key][1]['bottom_central'])

            logicFlowFromTwoDayRelationshipBasedOnH3AndL3 = serverside_functions.two_day_relationship(t_high=pivot_df[key][1]['R3'], t_low=pivot_df[key][1]['S3'], y_high=pivot_df[key][0]['R3'], y_low=pivot_df[key][0]['S3'], index=key)

            if key not in nextSessionCPRHistograms and key not in twoDayRelationshipBasedOnH3andL3data:
                nextSessionCPRHistograms[key] = {}
                twoDayRelationshipBasedOnH3andL3data[key] = {}
            nextSessionCPRHistograms[key] = nextSessionCprBreadth
            twoDayRelationshipBasedOnH3andL3data[key] = logicFlowFromTwoDayRelationshipBasedOnH3AndL3
        
            EOD_message = (
                "based on <b>intraday closing price</b>\n"
                f"tomorrow {key} Spot information based on Camarilla Pivot:\n\n"
                f"pivot: {pivot_df[key][1]['pivot']}\n"
                f"bottom central: {pivot_df[key][1]['bottom_central']}\n"
                f"top central: {pivot_df[key][1]['top_central']}\n\n"
                f"resistance::\nR1:: {pivot_df[key][1]['R1']}\nR2:: {pivot_df[key][1]['R2']}\nR3:: {pivot_df[key][1]['R3']}\nR4:: {pivot_df[key][1]['R4']}\nR5:: {pivot_df[key][1]['R5']}\n\n"
                f"support::\nS1:: {pivot_df[key][1]['S1']}\nS2:: {pivot_df[key][1]['S2']}\nS3:: {pivot_df[key][1]['S3']}\nS4:: {pivot_df[key][1]['S4']}\nS5:: {pivot_df[key][1]['S5']}\n\n"
                f"{nextSessionCPRHistograms[key]}\n"
                f"two day value area relationship: using CPR\n{twoDayRelationshipBasedOnCPRdata[key]}\n\n"
                f"two day value area relationship: using L3 & H3\n{twoDayRelationshipBasedOnH3andL3data[key]}\n\n"
                "⚠️ still in experimental stage::\n"
                "will improve on <b>EOD closing price.</b>"
            )

            serverside_functions.send_telegram_message(
                bot_token= telegram_bot_token,
                chat_id= personal_telegram_id,
                text= EOD_message
            )
