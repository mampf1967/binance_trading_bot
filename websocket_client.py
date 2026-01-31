"""
websocket_client.py - WebSocket connection management

VERSION 2.6 - CONDITIONAL INTERVAL SUBSCRIPTION
Subscribes only to enabled intervals (1m, 5m, or both)
"""

import websocket
import json
import ssl
import time


class WebSocketClient:
    """Manages WebSocket connection to Binance"""
    
    def __init__(self, symbols: list, interval: str, on_message_callback,
                 max_retries: int = 5, retry_delay: int = 10, 
                 active_intervals: list = None):
        """
        Initialize WebSocket client - CONDITIONAL INTERVALS
        
        Args:
            symbols: List of trading symbols (e.g., ['BTCUSDC', 'ETHUSDC'])
            interval: Legacy parameter (not used)
            on_message_callback: Callback function for messages
            max_retries: Maximum reconnection attempts
            retry_delay: Initial retry delay in seconds
            active_intervals: List of active intervals (e.g., ['1m'], ['5m'], or ['1m', '5m'])
        """
        self.symbols = symbols
        self.on_message_callback = on_message_callback
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Default to both intervals if not specified
        self.active_intervals = active_intervals if active_intervals else ['1m', '5m']
        
        self.ws = None
        self.should_stop = False
        self.retry_count = 0
        self.successful_data_received = False
        
        # Build combined stream URL - CONDITIONAL INTERVALS
        # Format: btcusdc@kline_1m/btcusdc@kline_5m/ethusdc@kline_1m/ethusdc@kline_5m
        streams = []
        for symbol in symbols:
            symbol_lower = symbol.lower()
            for interval in self.active_intervals:
                streams.append(f"{symbol_lower}@kline_{interval}")
        
        # Use combined stream endpoint (URL encoding)
        stream_names = "/".join(streams)
        #self.ws_url = f"wss://stream.binance.com:9443/stream?streams={stream_names}"
        self.ws_url = f"wss://stream.binance.com:443/stream?streams={stream_names}"
        
        print(f"🔗 WebSocket URL: {len(symbols)} symbols × {len(self.active_intervals)} intervals = {len(streams)} streams")
    
    def connect(self):
        """Connect to WebSocket"""
        while not self.should_stop and self.retry_count < self.max_retries:
            try:
                print(f"🔌 Connecting to WebSocket...")
                if self.retry_count > 0:
                    print(f"   Retry {self.retry_count}/{self.max_retries}")
                
                self.ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                
                # Run forever with relaxed ping settings
                self.ws.run_forever(
                    ping_interval=60,
                    ping_timeout=30,
                    sslopt={"cert_reqs": ssl.CERT_NONE}
                )
                
                # Connection closed
                if not self.successful_data_received:
                    self.retry_count += 1
                else:
                    self.retry_count = 0
                
                if not self.should_stop and self.retry_count < self.max_retries:
                    delay = min(self.retry_delay * (2 ** (self.retry_count - 1)), 300)
                    print(f"🔄 Reconnecting in {delay}s...")
                    time.sleep(delay)
                else:
                    break
                    
            except Exception as e:
                print(f"❌ WebSocket error: {e}")
                if self.retry_count >= self.max_retries:
                    break
                time.sleep(self.retry_delay)
        
        if self.retry_count >= self.max_retries:
            print(f"❌ Max retries ({self.max_retries}) reached")
    
    def _on_open(self, ws):
        """WebSocket opened"""
        print(f"✅ Connected to WebSocket")
        
        # Build interval description
        if len(self.active_intervals) == 2:
            interval_desc = "dual timeframe data (1m + 5m)"
        elif '1m' in self.active_intervals:
            interval_desc = "1min data only"
        elif '5m' in self.active_intervals:
            interval_desc = "5min data only"
        else:
            interval_desc = f"{', '.join(self.active_intervals)} data"
        
        print(f"📡 Streaming {interval_desc}")
        print()
    
    def _on_message(self, ws, message):
        """Handle incoming message"""
        try:
            data = json.loads(message)
            
            # Combined stream format: {"stream":"btcusdc@kline_1m","data":{...}}
            if "stream" in data and "data" in data:
                if not self.successful_data_received:
                    self.successful_data_received = True
                    self.retry_count = 0
                    print("✅ Data flowing normally")
                
                stream_name = data["stream"]
                # Extract symbol from stream (e.g., "btcusdc@kline_1m" -> "BTCUSDC")
                symbol = stream_name.split('@')[0].upper()
                kline = data["data"]["k"]
                
                # Call callback
                self.on_message_callback(symbol, kline)
                
        except Exception as e:
            print(f"❌ Error processing message: {e}")
    
    def _on_error(self, ws, error):
        """Handle WebSocket error"""
        print(f"⚠️  WebSocket error: {error}")
    
    def _on_close(self, ws, close_status_code=None, close_msg=None):
        """Handle WebSocket close"""
        if not self.should_stop:
            print(f"\n⚠️  WebSocket closed (code: {close_status_code})")
            if close_msg:
                print(f"   Message: {close_msg}")
    
    def stop(self):
        """Stop WebSocket connection"""
        self.should_stop = True
        if self.ws:
            try:
                self.ws.keep_running = False
            except:
                pass
            try:
                self.ws.close()
            except:
                pass
