import enum
from gps_ble_tracker import CombinedTracker
from transitions import Machine
from transitions.extensions import GraphMachine
import time

class TrackerState(enum.Enum):
    INITIALIZING = "initializing"
    SCANNING = "scanning"
    CONNECTING = "connecting"
    TRANSMITTING = "transmitting"
    ERROR = "error"

class StateMachineTracker(CombinedTracker):
    
    states = [state.value for state in TrackerState]

    def __init__(self, *args, **kwargs):

        if kwargs.get('ble_port') in ['none','None', 'NONE', None]:
            kwargs['ble_port'] = None
            self.ble_enabled = False
        else: self.ble_enabled = True


        self.machine = GraphMachine(
            model = self,
            states = self.states,
            initial = TrackerState.INITIALIZING.value
        )

        # transitions

        self.machine.add_transition(
            trigger='initialize_complete',
            source = TrackerState.INITIALIZING.value,
            dest = TrackerState.SCANNING.value
        )

        self.machine.add_transition(
            trigger='wifi_available',
            source = TrackerState.SCANNING.value,
            dest = TrackerState.CONNECTING.value
        )

        self.machine.add_transition(
            trigger='transmission_complete',
            source=TrackerState.CONNECTING.value,
            dest = TrackerState.SCANNING.value
        )

        self.machine.add_transition(
            trigger = 'transmission_failed',
            source=TrackerState.TRANSMITTING.value,
            dest= TrackerState.SCANNING.value
        )

        self.machine.add_transition(
            trigger='connection_failed',
            source=TrackerState.CONNECTING.value,
            dest = TrackerState.SCANNING.value
        )


        self.machine.add_transition(
            trigger='error_occured',
            source='*',
            dest= TrackerState.ERROR.value
        )


        self.machine.add_transition(
            trigger='error_resolved',
            source=TrackerState.ERROR.value,
            dest=TrackerState.SCANNING.value
        )

        self.pending_data = []
        self.last_wifi_check = 0
        self.wifi_check_interval = kwargs.get('wifi_check_interval',60)
        self.last_state_change = time.time(),
        self.machine.get_graph().draw('test.png',prog='dot')

def create_test_machine():
    tracker = StateMachineTracker(ble_port=None, wifi_check_interval=60)
    return tracker

if __name__ == "__main__":
    # Create the state machine
    tracker = create_test_machine()
    
    # The graph will be automatically generated as 'test.png'
    print("State machine graph has been generated as 'test.png'")
    
    print(f"Initial state: {tracker.state}")
    
    tracker.initialize_complete()
    print(f"After initialize_complete: {tracker.state}")
    
    tracker.wifi_available()
    print(f"After wifi_available: {tracker.state}")
    
    tracker.connection_failed()
    print(f"After connection_failed: {tracker.state}")
    
    tracker.error_occured()
    print(f"After error_occured: {tracker.state}")
    
    tracker.error_resolved()
    print(f"After error_resolved: {tracker.state}")


    #separation of the classes
    

































    











