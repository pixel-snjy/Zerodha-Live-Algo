Bugs to remove:
    1. ~~scrap access token at the day end or before market start.~~
    2. scrip is doing delay in taking trades; it took trades on next loop iteration.

Equity Swing trading:
    1. when price closes above CPR top pivot; go long until it closes below CPR bottom pivot. any timeframe.

CPR - Pivot Boss trades:
    1. define the trend from comparing previous session cpr+moneyZone to current session cpr+moneyZone
    2. swing high to swing low from any given data.
    3. cpr breadth calculation for sideways or trending session.
    4. L3 and below are buyer zones && R3 and above are seller zones.



To build a robust Python script based on the principles in *Secrets of a Pivot Boss*, your logic flow must transition from **data preparation** to **predictive forecasting** and, finally, to **real-time validation**. 

Following is the framework and logical approach for your script, structured around the "Flight Plan" methodology described in the sources.

### **Step 1: The Calculation Engine (Data Input)**
Your script must first ingest the **High, Low, and Close (HLC)** data from the prior period (Daily, Weekly, or Monthly) to generate the "Road Map" for the current session.
*   **Floor Pivots:** Calculate the Central Pivot (PP), Support (S1–S4), and Resistance (R1–R4).
*   **Central Pivot Range (CPR):** Specifically derive the Top Central (TC) and Bottom Central (BC).
*   **Camarilla Equation:** Calculate the H1–H5 and L1–L5 levels.
*   **Money Zone:** If you have time-price data, calculate the Value Area High (VAH), Value Area Low (VAL), and Point of Control (POC).

### **Step 2: The Forecasting Phase (Pre-Market Analysis)**
Before the market opens, the script should analyze the relationship between today’s pivots and yesterday’s price action to determine a **Directional Bias**.
*   **Pivot Width Analysis:** Compare the width of the CPR or Value Area. **Narrow pivots** should flag a "Trend Day" forecast, while **wide pivots** flag a "Sideways/Trading Range" forecast.
*   **Two-Day Relationships:** Determine if the current pivots are **Higher, Lower, Overlapping, or Inside** the previous day’s pivots. For example, an **Inside Value** relationship combined with narrow pivots is a high-conviction signal for an explosive breakout.

### **Step 3: Opening Print Validation (Conviction Check)**
Once the market opens, the script must compare the **Opening Price** to the calculated levels to see if the market "accepts" or "rejects" the forecast.
*   **Out of Range/Value Open:** If price opens beyond the prior day's range and today's pivots, it indicates high conviction from **initiative participants**.
*   **In-Value Open:** If price opens within the CPR or Value Area, it suggests a lack of conviction, favoring **responsive participants** and a sideways day.

### **Step 4: Hot Zone Identification (The Action Levels)**
The script should scan for **Multiple Pivot Hot Zones (MTZ)**—areas where pivots from different indicators or timeframes overlap.
*   **Golden Pivot Zone (GPZ):** Flag areas where a Money Zone level (like POC) or Camarilla level (like L3) falls inside the CPR. These are the highest-probability reversal or support zones.
*   **Confluence:** If an intraday pivot aligns with a Weekly or Monthly pivot, mark this as a "Heavy" support/resistance zone.

### **Step 5: Execution Trigger (Entry Logic)**
Do not enter based on a pivot touch alone. Your script should look for **Candlestick Signal Confirmation** at the identified Hot Zones.
*   **Reversal Triggers:** Look for a **Wick Reversal, Extreme Reversal, or Doji** when price hits a support/resistance pivot in a trend.
*   **Breakaway Triggers:** If price gaps beyond a pivot and holds it on a retest, trigger a "Breakaway Play".

### **Step 6: Trade Management (Exit Logic)**
Finally, the script manages the trade based on the forecasted day type.
*   **Trending Days:** Use a **Trailing Centrals Stop** (using the BC for longs or TC for shorts) to capture maximum range expansion.
*   **Sideways Days:** Use **Fixed Profit Targets** at the opposite pivot levels (e.g., enter at L3, exit at H3).

***

**The "GPS" Analogy:**
Think of your Python script as a **Satellite Navigation System**. The **Calculation Engine** is your map; the **Forecasting Phase** is your intended route; and the **Opening Print Validation** is the "Live Traffic" update. If the traffic (Opening Price) doesn't match your route, the script must "recalculate" the conviction level before you step on the accelerator (Enter the trade).