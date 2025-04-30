import subprocess
import time
import datetime
import re
import os

def scan_networks():
    # Get a list of wireless interfaces
    interfaces = []
    iwconfig_result = subprocess.run(['iwconfig'], capture_output=True, text=True)
    for line in iwconfig_result.stdout.split('\n'):
        if 'IEEE 802.11' in line:  # This indicates a wireless interface
            interfaces.append(line.split()[0])
    
    # Dictionary to store all networks
    networks = {}
    
    # Scan each interface
    for interface in interfaces:
        try:
            # Run scan command
            scan_result = subprocess.run(['sudo', 'iwlist', interface, 'scan'], 
                                         capture_output=True, text=True)
            
            if scan_result.returncode != 0:
                print(f"Error scanning with {interface}: {scan_result.stderr}")
                continue
                
            output = scan_result.stdout
            
            # Parse the output to extract network information
            current_cell = None
            current_network = {}
            
            for line in output.split('\n'):
                line = line.strip()
                
                # New cell/network found
                if line.startswith('Cell '):
                    # Save previous network if it exists
                    if current_cell and current_network:
                        networks[current_cell] = current_network
                    
                    # Start new network
                    cell_match = re.search(r'Cell (\d+) - Address: ([0-9A-F:]+)', line)
                    if cell_match:
                        current_cell = f"{interface}_{cell_match.group(1)}_{cell_match.group(2)}"
                        current_network = {'interface': interface, 'address': cell_match.group(2)}
                
                # Extract ESSID
                elif 'ESSID:' in line:
                    essid_match = re.search(r'ESSID:"([^"]*)"', line)
                    if essid_match:
                        current_network['essid'] = essid_match.group(1)
                
                # Extract Channel
                elif 'Channel:' in line:
                    channel_match = re.search(r'Channel:(\d+)', line)
                    if channel_match:
                        current_network['channel'] = int(channel_match.group(1))
                
                # Extract Frequency
                elif 'Frequency:' in line:
                    freq_match = re.search(r'Frequency:(\d+\.\d+) GHz', line)
                    if freq_match:
                        current_network['frequency'] = float(freq_match.group(1))
                
                # Extract Quality
                elif 'Quality=' in line:
                    quality_match = re.search(r'Quality=(\d+)/(\d+)', line)
                    if quality_match:
                        quality_value = int(quality_match.group(1))
                        quality_max = int(quality_match.group(2))
                        quality_percent = (quality_value / quality_max) * 100
                        current_network['quality'] = quality_percent
                        current_network['quality_raw'] = f"{quality_value}/{quality_max}"
                    
                    # Extract Signal Level (often on same line as Quality)
                    signal_match = re.search(r'Signal level=(-?\d+) dBm', line)
                    if signal_match:
                        current_network['signal'] = int(signal_match.group(1))
                
                # Extract Encryption
                elif 'Encryption key:' in line:
                    encryption_match = re.search(r'Encryption key:(on|off)', line)
                    if encryption_match:
                        current_network['encryption'] = encryption_match.group(1) == 'on'
                
                # Extract IE (Information Element) for security protocols
                elif 'IE:' in line:
                    if 'security_protocols' not in current_network:
                        current_network['security_protocols'] = []
                    
                    # WPA/WPA2
                    if 'WPA' in line:
                        current_network['security_protocols'].append(line.strip())
                
                # Extract Bit Rates
                elif 'Bit Rates:' in line:
                    rates = re.findall(r'(\d+\.\d+) Mb/s', line)
                    if rates:
                        if 'bit_rates' not in current_network:
                            current_network['bit_rates'] = []
                        current_network['bit_rates'].extend([float(rate) for rate in rates])
            
            # Save the last network
            if current_cell and current_network:
                networks[current_cell] = current_network
                
        except Exception as e:
            print(f"Error scanning with {interface}: {str(e)}")
    
    return networks

def log_network_scan():
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    networks = scan_networks()
    
    # Create logs directory if it doesn't exist
    if not os.path.exists('wifi_logs'):
        os.makedirs('wifi_logs')
    
    # Log all networks to a single file
    log_file = f"wifi_logs/network_scan_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    with open(log_file, 'w') as f:
        f.write(f"=== WiFi Network Scan: {timestamp} ===\n\n")
        
        for cell_id, network in networks.items():
            f.write(f"Network: {network.get('essid', 'Unknown')}\n")
            f.write(f"  Interface: {network.get('interface', 'N/A')}\n")
            f.write(f"  MAC Address: {network.get('address', 'N/A')}\n")
            if 'channel' in network:
                f.write(f"  Channel: {network['channel']}\n")
            if 'frequency' in network:
                f.write(f"  Frequency: {network['frequency']} GHz\n")
            if 'quality' in network:
                f.write(f"  Quality: {network['quality']:.1f}% ({network.get('quality_raw', 'N/A')})\n")
            if 'signal' in network:
                f.write(f"  Signal: {network['signal']} dBm\n")
            if 'encryption' in network:
                f.write(f"  Encryption: {'Enabled' if network['encryption'] else 'Disabled'}\n")
            if 'security_protocols' in network:
                f.write(f"  Security: {', '.join(network['security_protocols'])}\n")
            if 'bit_rates' in network:
                f.write(f"  Bit Rates: {', '.join([f'{rate} Mb/s' for rate in network['bit_rates']])}\n")
            f.write("\n")
    
    # Print to console as well
    print(f"=== WiFi Network Scan: {timestamp} ===")
    print(f"Found {len(networks)} networks")
    
    # Sort networks by signal strength if available
    sorted_networks = sorted(
        networks.values(), 
        key=lambda x: x.get('signal', 0), 
        reverse=True
    )
    
    for network in sorted_networks:
        print(f"Network: {network.get('essid', 'Unknown')}")
        print(f"  Interface: {network.get('interface', 'N/A')}")
        print(f"  Channel: {network.get('channel', 'N/A')}")
        if 'quality' in network:
            print(f"  Quality: {network['quality']:.1f}%")
        if 'signal' in network:
            print(f"  Signal: {network['signal']} dBm")
        if 'encryption' in network:
            print(f"  Encryption: {'Enabled' if network['encryption'] else 'Disabled'}")
        if 'security_protocols' in network and network['security_protocols']:
            print(f"  Security: {network['security_protocols'][0]}")
        print("")
    
    print(f"Detailed scan saved to {log_file}")
    return log_file

def main():
    print("Starting WiFi network scanner...")
    
    try:
        while True:
            print("\nScanning for networks...")
            log_file = log_network_scan()
            
            # Ask if user wants to scan again
            choice = input("\nScan again? (y/n): ").strip().lower()
            if choice != 'y':
                break
                
    except KeyboardInterrupt:
        print("\nScanning stopped.")

if __name__ == "__main__":
    main()