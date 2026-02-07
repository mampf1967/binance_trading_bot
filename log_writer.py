"""
log_writer.py - File logging operations

Handles all file-based logging with timestamp formatting.
"""

import os
from pathlib import Path
from datetime import datetime
from console_formatter import strip_ansi_codes


class LogWriter:
    """Handles file logging for trading bot"""
    
    def __init__(self, name: str = "bot", log_to_file: bool = True):
        """
        Initialize log writer
        
        Args:
            name: Logger name (used for filename)
            log_to_file: Whether to enable file logging
        """
        self.name = name
        self.log_to_file = log_to_file
        self.file_handle = None
        
        if log_to_file:
            self._init_log_file()
    
    def _init_log_file(self):
        """Initialize log file in append mode"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"{self.name}.log"
        file_exists = log_file.exists()
        
        self.file_handle = open(log_file, 'a', encoding='utf-8')
        
        if not file_exists:
            self.file_handle.write(f"=== {self.name} Log Started ===\n")
            self.file_handle.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.file_handle.write("=" * 70 + "\n\n")
        else:
            self.file_handle.write(f"\n\n=== Session Resumed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
        
        self.file_handle.flush()
    
    def write(self, message: str, timestamp: str = None):
        """
        Write message to log file
        
        Args:
            message: Message to write (may contain ANSI codes)
            timestamp: Optional timestamp string (HH:MM format)
        """
        if not self.log_to_file or not self.file_handle:
            return
        
        # Use provided timestamp or current time
        if not timestamp:
            timestamp = datetime.now().strftime('%H:%M')
        
        # Strip ANSI codes for clean file output
        clean_message = strip_ansi_codes(message)
        
        # Write with timestamp prefix if message doesn't have one
        if not clean_message.startswith(timestamp):
            self.file_handle.write(f"{timestamp} {clean_message}\n")
        else:
            self.file_handle.write(f"{clean_message}\n")
        
        self.file_handle.flush()
    
    def write_raw(self, message: str):
        """Write raw message without timestamp"""
        if not self.log_to_file or not self.file_handle:
            return
        
        clean_message = strip_ansi_codes(message)
        self.file_handle.write(f"{clean_message}\n")
        self.file_handle.flush()
    
    def write_separator(self, length: int = 70):
        """Write separator line"""
        if not self.log_to_file or not self.file_handle:
            return
        
        self.file_handle.write("=" * length + "\n")
        self.file_handle.flush()
    
    def close(self):
        """Close log file"""
        if self.file_handle:
            self.file_handle.write("\n" + "=" * 70 + "\n")
            self.file_handle.write(f"=== Log Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            self.file_handle.close()
            self.file_handle = None
