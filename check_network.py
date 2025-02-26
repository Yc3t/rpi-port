import subprocess
import time
import datetime
import re
import os

def get_wifi_quality():
    # Run iwconfig command to get wireless interface information
    result = subprocess.run(['iwconfig'], capture_output=True, text=True)
    output = result.stdout
    
    # Dictionary to store interface data
    interfaces = {}
    
    # Parse the output to extract interface names and their quality information
    current_interface = None
    for line in output.split('\n'):
        # Check if this is a new interface line
        if not line.startswith(' ') and line.strip():
            parts = line.split()
            if len(parts) > 0:
                current_interface = parts[0]
                interfaces[current_interface] = {}
        
        # If we have a current interface, extract quality information
        elif current_interface and "Link Quality" in line:
            # Extract Link Quality
            quality_match = re.search(r'Link Quality=(\d+)/(\d+)', line)
            if quality_match:
                quality_value = int(quality_match.group(1))
                quality_max = int(quality_match.group(2))
                quality_percent = (quality_value / quality_max) * 100
                interfaces[current_interface]['quality'] = quality_percent
            
            # Extract Signal Level
            signal_match = re.search(r'Signal level=(-?\d+) dBm', line)
            if signal_match:
                signal_level = int(signal_match.group(1))
                interfaces[current_interface]['signal'] = signal_level
    
    # Filter out interfaces without wireless extensions
    return {k: v for k, v in interfaces.items() if v}

def log_wifi_quality():
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    wifi_data = get_wifi_quality()
    
    # Create logs directory if it doesn't exist
    if not os.path.exists('wifi_logs'):
        os.makedirs('wifi_logs')
    
    # Log data for each wireless interface
    for interface, data in wifi_data.items():
        if data:  # Only log if we have data
            log_file = f"wifi_logs/{interface}_quality.log"
            
            with open(log_file, 'a') as f:
                f.write(f"{timestamp} - Interface: {interface} - ")
                f.write(f"Quality: {data.get('quality', 'N/A'):.1f}% - ")
                f.write(f"Signal: {data.get('signal', 'N/A')} dBm\n")
    
    # Print to console as well
    print(f"=== WiFi Quality Check: {timestamp} ===")
    for interface, data in wifi_data.items():
        if data:
            print(f"Interface: {interface}")
            print(f"  Quality: {data.get('quality', 'N/A'):.1f}%")
            print(f"  Signal: {data.get('signal', 'N/A')} dBm")
    print("")

def main():
    print("Starting WiFi quality monitoring (every 5 seconds)...")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            log_wifi_quality()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

if __name__ == "__main__":
    main()