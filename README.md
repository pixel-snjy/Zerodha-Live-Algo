# Zerodha Live Algo

A Python-based algorithmic trading system designed to automate trading strategies using the Zerodha trading platform API. The project demonstrates how market data can be analyzed using technical indicators to generate trading signals and automate trade execution.

This project explores algorithmic trading workflows including data collection, strategy development, technical indicator analysis, and automated order execution.

---

# Features

* Automated trading using Zerodha API
* Market data analysis using Python
* Implementation of technical indicators such as:

  * RSI (Relative Strength Index)
  * SMA (Simple Moving Average)
  * EMA (Exponential Moving Average)
  * Bollinger Bands
* Strategy backtesting using historical data
* Signal generation based on technical analysis
* Modular Python structure for experimenting with trading strategies

Algorithmic trading systems use APIs to connect with brokerage platforms and execute trades automatically based on predefined strategies. ([GitHub][1])

---

# Project Structure

```
Zerodha-Live-Algo
│
├── indicators/        # Technical indicators implementations
├── strategies/        # Trading strategy logic
├── data/              # Historical or processed market data
├── main.py            # Main script to run trading logic
├── requirements.txt   # Project dependencies
└── README.md
```

---

# Technologies Used

* Python
* Pandas
* NumPy
* Matplotlib
* Zerodha Kite API
* REST API integration

---

# Installation

Clone the repository:

```bash
git clone https://github.com/pixel-snjy/Zerodha-Live-Algo.git
```

Navigate to the project directory:

```bash
cd Zerodha-Live-Algo
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate the environment:

Linux / Mac

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

# Usage

1. Configure your Zerodha API credentials.
2. Select the trading strategy or indicator you want to test.
3. Run the main script:

```bash
python main.py
```

The system will:

* Fetch market data
* Analyze indicators
* Generate trading signals
* Execute trades automatically (if enabled)

---

# Example Strategies

Some strategies implemented or explored in this project include:

* Moving Average crossover strategies
* RSI-based entry and exit signals
* Trend-following strategies
* Indicator-based stock screening

---

# Learning Outcomes

Through this project I gained hands-on experience with:

* Financial data analysis
* Algorithmic trading concepts
* API integration
* Strategy backtesting
* Automation using Python

---

# Disclaimer

This project is intended for **educational purposes only**.

Trading in financial markets involves significant risk. The strategies and code provided here should not be considered financial advice. Always test strategies thoroughly before deploying them in live trading environments.

---

# Author

**Sanjay Lunayach**

GitHub:
[https://github.com/pixel-snjy](https://github.com/pixel-snjy)
