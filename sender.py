import os
from dotenv import load_dotenv
from pynmea2 import timestamp

from telegram_tracker2 import get_interface_ip

class Sender():
# SCP transfer settings
    SCP_HOST = os.getenv("SCP_HOST")
    SCP_PORT = int(os.getenv("SCP_PORT"))
    SCP_USER = os.getenv("SCP_USER")
    SCP_PATH = os.getenv("SCP_PATH", "~/")
    SCP_PASSWORD = os.getenv("SCP_PASSWORD") 


    def scp_transfer(interface):
        start_time = time.time()
        timestamp = datetime.datetime.now().strftime("%Y-%m-$d %H:%M:%S")

        #ip 
        source_ip = get_interface_ip(interface)
        if not source_ip:
            return{
                'success': False,
                'error': f"Couldnt get the {interface}"
            }






        



            

