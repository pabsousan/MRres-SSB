from opentrons.simulate import simulate
from io import StringIO  # For wrapping the string as a file-like object
import inspect
logger = None  # Global logger instance

class LoggerDecorator:
    def __init__(self, context):
        self.context = context
        self.logs = []
        self.well_volumes = {}  # Tracks well volumes
        self.well_capacity = {}  # Tracks max capacity for each well
        self.tip_usage = {}  # Dynamic tip counters per tip type
        self.flow_rates = {}  # Dynamic flow rates per tip type
        self.error_flag = False  # Flag for errors
        self.labware_names = {}  # Maps labware objects to variable names in the protocol
        #print("LoggerDecorator initialized.")


    def _format_log(self, level, message):
        """Format log messages with color and level."""
        levels = {
            "ACTION": "\033[32m[ACTION]\033[0m",  # Green
            "ERROR": "\033[31m[ERROR]\033[0m",    # Red
            "INFO": "\033[36m[INFO]\033[0m"       # Cyan
        }
        return f"{levels.get(level, '')} {message}"

    def log_action(self, action: str):
        """Log an action."""
        message = self._format_log("ACTION", action)
        print(message)
        self.logs.append({"action": action})

    def log_error(self, error_message: str):
        """Log an error and pause the simulation."""
        message = self._format_log("ERROR", error_message)
        print(message)
        self.logs.append({"action": f"ERROR: {error_message}"})
        input("\nPress Enter to continue...")

    def log_info(self, info_message: str):
        """Log debugging information."""
        message = self._format_log("INFO", info_message)
        print(message)

    def set_labware_names(self, protocol):
        """Dynamically map labware objects to their variable names."""
        for name, obj in inspect.getmembers(protocol):
            if hasattr(obj, "wells"):  # Check for well-containing labware
                self.labware_names[obj] = name

    def get_labware_name(self, labware):
        """Retrieve the variable name of the labware."""
        return self.labware_names.get(labware, labware.name)  # Default to product name if not mapped

    def wrap_instrument(self, instrument):
        """Wrap instrument methods for logging."""
        if instrument is None:
            raise ValueError("Cannot wrap a NoneType instrument.")
        
        # Wrap pipetting methods
        instrument.aspirate = self.decorate(instrument.aspirate)
        instrument.dispense = self.decorate(instrument.dispense)
        instrument.pick_up_tip = self.decorate(instrument.pick_up_tip)
        instrument.drop_tip = self.decorate(instrument.drop_tip)
        
        # Wrap flow_rate object with dynamic tracking
        self.wrap_flow_rate(instrument)
        self.log_initial_flow_rates(instrument)  # Log initial flow rates
        return instrument

    def wrap_flow_rate(self, pipette):
        """Dynamically wrap flow_rate attributes (aspirate, dispense, blow_out) to track changes."""
        flow_rate = pipette.flow_rate  # Get the existing flow_rate object

        # Define a helper function to create a logged property for flow rates
        def create_logged_property(attribute):
            class LoggedFlowRateProperty:
                """Class to encapsulate and log the flow rate updates."""

                def __init__(self, logger_decorator, pipette, attribute):
                    self.logger_decorator = logger_decorator
                    self.pipette = pipette
                    self.attribute = attribute
                    self._original_value = getattr(flow_rate, attribute)

                def __get__(self, instance, owner):
                    # Return the current value of the flow rate
                    return self._original_value

                def __set__(self, instance, value):
                    if not isinstance(value, (int, float)):
                        raise ValueError(f"{self.attribute} flow rate must be a numerical value in µL/s.")
                    # Update the flow rate and log the change
                    self._original_value = value
                    self.logger_decorator.log_flow_rate_change(self.pipette, self.attribute, value)

            return LoggedFlowRateProperty(self, pipette, attribute)

        # Wrap the relevant flow_rate attributes
        for attr in ["aspirate", "dispense", "blow_out"]:
            logged_property = create_logged_property(attr)
            setattr(flow_rate.__class__, attr, logged_property)
            
        # Update flow rates for this pipette's tip type
        tip_type = self.get_dynamic_tip_type(pipette)
        if tip_type not in self.flow_rates:
            self.flow_rates[tip_type] = {
                "aspirate": pipette.flow_rate.aspirate,
                "dispense": pipette.flow_rate.dispense,
                "blow_out": pipette.flow_rate.blow_out,
            }

    def log_initial_flow_rates(self, pipette):
        """Log the initial flow rates for the pipette."""
        tip_type = self.get_dynamic_tip_type(pipette)
        self.flow_rates[tip_type] = {
            "aspirate": pipette.flow_rate.aspirate,
            "dispense": pipette.flow_rate.dispense,
            "blow_out": pipette.flow_rate.blow_out,
        }
        self.log_info(
            f"Initial flow rates for {tip_type}: Aspirate={self.flow_rates[tip_type]['aspirate']} µL/s, "
            f"Dispense={self.flow_rates[tip_type]['dispense']} µL/s, "
            f"Blow-out={self.flow_rates[tip_type]['blow_out']} µL/s."
        )

    def log_flow_rate_change(self, pipette, action, value):
        """Log specific flow rate changes for a pipette based on tip type."""
        tip_type = self.get_dynamic_tip_type(pipette)
        self.flow_rates.setdefault(tip_type, {
            "aspirate": pipette.flow_rate.aspirate,
            "dispense": pipette.flow_rate.dispense,
            "blow_out": pipette.flow_rate.blow_out
        })
        self.flow_rates[tip_type][action] = value
        self.log_info(
            f"Flow rate for {action} updated to {value} µL/s for {tip_type}."
        )

    def track_volume(self, volume: float, source=None, destination=None, rate=None, tip_type=None):
        """Track liquid volumes and handle realistic behavior."""
        def parse_location(location):
            """Parse location to extract meaningful details."""
            if "point=" in str(location):  # Custom coordinate in the well
                point_details = str(location).split("point=")[-1].strip("()").split(", ")
                return f"custom coordinates (x={point_details[0]}, y={point_details[1]}, z={point_details[2]})"

            if hasattr(location, 'parent'):  # For wells or well-like objects
                slot_info = location.parent.parent  # Access slot number from labware
                labware_name = location.parent.name  # Access labware name
                if "module" in str(location.parent).lower():
                    module_name = str(location.parent).split(" ")[0]
                    return f"'{module_name}' on slot {slot_info} ({labware_name})"
                return f"slot {slot_info} ({labware_name})"

            if "slot" in str(location):  # For generic locations with slot info
                slot_info = str(location).split("slot")[-1].split("=")[-1].strip(")").strip()
                return f"slot {slot_info}"

            return "unknown location"

        # Generate unique identifiers for source/destination wells
        def well_key(well):
            if well is None:
                return None
            return (well.display_name if hasattr(well, 'display_name') else "unknown",
                    well.parent if hasattr(well, 'parent') else None)
        
        # Calculate effective flow rate
        def get_effective_rate(base_rate, multiplier):
            try:
                return base_rate * multiplier if multiplier else base_rate
            except TypeError:
                return base_rate  # Fallback if multiplier is invalid

        # Determine tip type dynamically
        if not tip_type:
            tip_type = "unknown tip type"

        if source:
            # Extract well name, labware variable name, and slot number
            source_key = well_key(source)
            source_details = parse_location(source)
            well_name = source.display_name.split(' ')[0] if hasattr(source, 'display_name') else "unknown"
            
            # Track volume for aspiration
            available_volume = self.well_volumes.get(source_key, 0)
            aspirated_volume = min(available_volume, volume)
            effective_rate = get_effective_rate(self.flow_rates[tip_type]["aspirate"], rate)
            self.well_volumes[source_key] = max(0, available_volume - aspirated_volume)

            # Log aspirate action
            self.log_action(
                f"{tip_type} aspirated {aspirated_volume} µL from {well_name} ({source_details}) "
                f"at {effective_rate:.2f} µL/s. Remaining: {self.well_volumes[source_key]} µL."
            )
            if available_volume < volume:
                self.log_error(
                    f"Tried to aspirate {volume} µL from {well_name} ({source_details}), "
                    f"but only {available_volume} µL was available. Aspirated what was left."
                )

        if destination:
            # Extract well name, labware variable name, and slot number
            destination_key = well_key(destination)
            destination_details = parse_location(destination)
            well_name = destination.display_name.split(' ')[0] if hasattr(destination, 'display_name') else "unknown"
            
            # Track volume for dispensing
            current_volume = self.well_volumes.get(destination_key, 0)
            max_capacity = self.well_capacity.get(destination_key, float('inf'))
            new_volume = current_volume + volume
            dispensed_volume = min(volume, max_capacity - current_volume)
            effective_rate = get_effective_rate(self.flow_rates[tip_type]["dispense"], rate)
            self.well_volumes[destination_key] = min(new_volume, max_capacity)

            # Log dispense action
            self.log_action(
                f"{tip_type} dispensed {dispensed_volume} µL into {well_name} ({destination_details}) "
                f"at {effective_rate:.2f} µL/s. Total: {self.well_volumes[destination_key]} µL."
            )
            if new_volume > max_capacity:
                self.log_error(
                    f"Tried to dispense {volume} µL into {well_name} ({destination_details}), "
                    f"but it exceeds capacity. Adjusted to the maximum capacity of {max_capacity} µL."
                )

    def get_dynamic_tip_type(self, pipette):
        """Determine the dynamic tip type based on the pipette's tip rack."""
        if pipette.tip_racks and pipette.tip_racks[0].load_name:
            rack_name = pipette.tip_racks[0].load_name
            # Extract the tip type dynamically, e.g., "300ul" → "p300"
            parts = rack_name.split('_')
            for part in parts:
                if part.endswith('ul'):
                    try:
                        return f"p{int(part[:-2])}"
                    except ValueError:
                        pass
        return "unknown tip type"

    def decorate(self, func):
        """Decorator to wrap functions for logging."""
        def wrapper(*args, **kwargs):
            # Debugging: Print args and kwargs
            self.log_info(f"Decorating: {func.__name__}, args={args}, kwargs={kwargs}")
            #self.log_info(f"Type of args: {type(args)}, Type of kwargs: {type(kwargs)}")
            
            # Extract volume, location, and rate, handling both args and kwargs
            volume = kwargs.get("volume", args[0] if len(args) > 0 else None)
            location = kwargs.get("location", args[1] if len(args) > 1 else None)
            #rate = self.flow_rates.get(func.__name__, "unknown")
            rate = kwargs.get("rate", None)
            repetitions = kwargs.get("repetitions", None)


            # Debugging aspirate/dispense actions
            #self.log_info(f"{func.__name__.capitalize()}: Volume={volume}, Location={location}, Rate={rate}")

            # Determine the pipette from the bound method
            pipette = getattr(func, "__self__", None)
            if pipette is None:
                self.log_error(f"Unable to identify pipette for method {func.__name__}.")
                return func(*args, **kwargs)  # Proceed without enhanced logging

            # Extract the tip type dynamically
            tip_type = self.get_dynamic_tip_type(pipette)

            # Handle mix action
            if func.__name__ == "mix":
                if location is None or not hasattr(location, 'parent'):
                    self.log_error("Mix action requires a valid location with well-like properties.")
                else:
                    # Log mix action details
                    well_name = location.display_name.split(' ')[0] if hasattr(location, 'display_name') else "unknown"
                    location_details = f"{self.get_labware_name(location.parent)} {well_name}"
                    effective_rate = rate or 1.0  # Default to a rate of 1.0 if not specified
                    self.log_action(
                        f"{tip_type} mixed {repetitions} times with {volume} µL in {location_details} "
                        f"at {effective_rate:.2f}x speed."
                    )

            # Handle aspirate and dispense actions
            elif func.__name__ == "aspirate":
                self.track_volume(volume, source=location, rate=rate, tip_type=tip_type)
            elif func.__name__ == "dispense":
                self.track_volume(volume, destination=location, rate=rate, tip_type=tip_type)

            # Handle pick_up_tip and drop_tip actions
            elif func.__name__ == "pick_up_tip":
                if tip_type not in self.tip_usage:
                    self.tip_usage[tip_type] = 0
                self.tip_usage[tip_type] += 1
                self.log_action(f"Picked up a new {tip_type} tip. Total {tip_type} tips used: {self.tip_usage[tip_type]}.")
            elif func.__name__ == "drop_tip":
                self.log_action(f"Dropped a {tip_type} tip.")

            # Handle blow_out with effective rate
            elif func.__name__ == "blow_out":
                effective_rate = self.flow_rates.get(tip_type, {}).get("blow_out", "unknown")
                effective_rate = effective_rate * rate if rate else effective_rate
                location_details = self.track_blowout(location, rate)
                self.log_action(
                    f"Performed blow_out at {location_details} at {effective_rate:.2f} µL/s for {tip_type}."
                )

            # Handle flow rate updates
            elif func.__name__ in ["set_flow_rate"]:
                action = kwargs.get("action", None)
                value = kwargs.get("value", None)
                if action and value:
                    pipette = args[0] if len(args) > 0 else None
                    self.track_flow_rate(pipette, action, value)

            # Handle tip-related actions
            elif func.__name__ == "pick_up_tip":
                self.tip_usage += 1
                self.log_action(f"Picked up a new tip. Total tips used: {self.tip_usage}.")
            elif func.__name__ == "drop_tip":
                self.log_action("Dropped a tip.")

            # Handle thermocycler temperature actions
            elif func.__name__ == "set_block_temperature":
                temperature = kwargs.get("temperature", args[0] if len(args) > 0 else None)
                self.log_action(f"Set thermocycler block temperature to {temperature} °C.")
            elif func.__name__ == "set_lid_temperature":
                temperature = kwargs.get("temperature", args[0] if len(args) > 0 else None)
                self.log_action(f"Set thermocycler lid temperature to {temperature} °C.")

            # Handle thermocycler lid actions
            elif func.__name__ == "close_lid":
                self.log_action("Closed thermocycler lid.")
            elif func.__name__ == "open_lid":
                self.log_action("Opened thermocycler lid.")

            # Handle module actions
            elif func.__name__ == "engage":
                height = kwargs.get("height_from_base", "default height")
                self.log_action(f"Engaged magnetic module at {height} mm from base.")
            elif func.__name__ == "disengage":
                self.log_action("Disengaged magnetic module.")

            # Handle potential catch-all logs
            else:
                action_desc = f"{func.__name__.replace('_', ' ').capitalize()} {args} {kwargs}"
                self.log_action(f"Executing: {action_desc}")

            return func(*args, **kwargs)
        return wrapper

    def wrap_module(self, module):
        """Wrap module methods for logging."""
        if hasattr(module, "engage"):
            module.engage = self.decorate(module.engage)
        if hasattr(module, "disengage"):
            module.disengage = self.decorate(module.disengage)
        if hasattr(module, "set_block_temperature"):
            module.set_block_temperature = self.decorate(module.set_block_temperature)
        if hasattr(module, "set_lid_temperature"):
            module.set_lid_temperature = self.decorate(module.set_lid_temperature)
        if hasattr(module, "close_lid"):
            module.close_lid = self.decorate(module.close_lid)
        if hasattr(module, "open_lid"):
            module.open_lid = self.decorate(module.open_lid)
        return module

    def get_logs(self):
        """Return the complete logs."""
        return self.logs

    def get_tip_usage(self):
        """Return the total tips used."""
        return self.tip_usage


if __name__ == "__main__":
    # Unified protocol file variable
    #protocol_file_name = "Frankenstein.py"
    protocol_file_name = "api_stressor.py"

    # Open the protocol script file
    with open(protocol_file_name, "r") as f:
        protocol_contents = f.read()

    # Wrap the contents in a StringIO object
    protocol_io = StringIO(protocol_contents)

    # Import the protocol's logger initialization dynamically
    protocol_module = __import__(protocol_file_name.replace(".py", ""))
    initialize_logger = getattr(protocol_module, "initialize_logger", None)
    if initialize_logger is not None:
        initialize_logger(None)  # Initialize the logger in the simulation context
    else:
        print(f"Warning: 'initialize_logger' not found in {protocol_file_name}")

    # Simulate the protocol
    from Select_SELEX import initialize_logger  #test_protocol_script
    initialize_logger(None)  # Initialize the logger in the simulation context
    runlog, context = simulate(protocol_io)

    # Output the simulation run log (optional)
    if runlog:
        print("\nSimulation Log Output:")
        for entry in runlog:
            print(entry)
    else:
        print("Simulation returned an empty runlog.")