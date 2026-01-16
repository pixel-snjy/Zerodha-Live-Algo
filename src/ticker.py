import time
import datetime
from kiteconnect import KiteTicker

class LiveTicker:
    def __init__(self, api_key, access_token):
        self.kws = KiteTicker(api_key, access_token)
        self.live_data = {}  # Shared storage for latest ticks
        self.tokens_to_subscribe = []
        
        # Assign callbacks
        self.kws.on_ticks = self.on_ticks
        self.kws.on_connect = self.on_connect
        self.kws.on_error = self.on_error

    def start(self, tokens):
        """Starts the WebSocket in a background thread."""
        self.tokens_to_subscribe = tokens
        # threaded=True allows main.py to keep running
        self.kws.connect(threaded=True)

    def on_ticks(self, ws, ticks):
        """Updates the shared dictionary whenever data comes in."""
        for tick in ticks:
            token = tick['instrument_token']
            # Store the full tick data so we can access it anytime
            self.live_data[token] = tick

    def on_connect(self, ws, response):
        """Subscribes to tokens on connection."""
        ws.subscribe(self.tokens_to_subscribe)
        ws.set_mode(ws.MODE_QUOTE, self.tokens_to_subscribe)
        # print(f"✅ Ticker Connected. Subscribed to: {self.tokens_to_subscribe}")

    def on_error(self, ws, code, reason):
        print(f"❌ Ticker Error: {code} - {reason}")

    def get_open_price(self, token_id):
        """
        BLOCKING METHOD:
        Waits until the market is open AND we have received data for this token.
        Returns the open price, but keeps the connection alive.
        """
        # print(f"⏳ Waiting for Open (First Tick) for token {token_id}...")
        
        while True:
            # 1. Check if Market is Open (09:15)
            now = datetime.datetime.now().time()
            start_time = datetime.time(9, 15)
            
            if now >= start_time:
                # 2. Check if we have received data from WebSocket
                if token_id in self.live_data:
                    tick = self.live_data[token_id]
                    # open_price = tick['ohlc']['open']
                    first_tick_price = tick['last_price']
                    
                    if first_tick_price > 0:
                        # print(f"✅ Found First Tick Price: {first_tick_price}")
                        return first_tick_price
                    # else:
                    #     continue
            
            # Sleep specifically to prevent CPU spikes while waiting
            time.sleep(0.01)

    def get_latest_tick(self, token_id):
        """Helper to get current data instantly (non-blocking)."""
        return self.live_data.get(token_id, None)

    def subscribe_new_tokens(self, tokens):
        """
        Dynamically subscribes to new tokens without restarting the script.
        """
        # Ensure input is a list
        if not isinstance(tokens, list):
            tokens = [tokens]
            
        # 1. Update internal list (so they are re-subscribed if connection drops & reconnects)
        for t in tokens:
            if t not in self.tokens_to_subscribe:
                self.tokens_to_subscribe.append(t)
        
        # 2. Send command to Kite (safely wrapped)
        try:
            self.kws.subscribe(tokens)
            # IMPORTANT: Set mode to QUOTE (or FULL) to get prices
            self.kws.set_mode(self.kws.MODE_QUOTE, tokens)
            print(f"✅ Dynamically Subscribed to: {tokens}")
        except Exception as e:
            print(f"⚠️ Connection not active, will subscribe on reconnect: {e}")

    def unsubscribe_tokens(self, tokens):
        """
        Stop tracking specific tokens.
        """
        if not isinstance(tokens, list):
            tokens = [tokens]

        # 1. Remove from internal list
        self.tokens_to_subscribe = [t for t in self.tokens_to_subscribe if t not in tokens]
        
        # 2. Send command
        try:
            self.kws.unsubscribe(tokens)
            # Optional: Clean up old data from memory
            for t in tokens:
                self.live_data.pop(t, None) 
            print(f"✅ Unsubscribed from: {tokens}")
        except Exception as e:
            print(f"⚠️ Error unsubscribing: {e}")