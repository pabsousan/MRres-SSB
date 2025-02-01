# Metadata
metadata = {
    'protocolName': 'Pt 1. FULL PROTOCOL',
    'author': 'Pablo Sousa-Sanchez, Harry Doherty, Chris Schade, & Will Green',
    'description': 'Automates Directed Evolution: epPCR library prep with varying dNTP and manganese levels, then conducts SELEX with increasing filter strength.',
    'apiLevel': '2.15'
}

# Initialize a global logger variable
logger = None

def initialize_logger(protocol):
    """
    Initialize the logger dynamically.
    Includes fallback so logger_decorator.py doesn't need to be present in the Opentron App
    """
    global logger
    try:
        from logger_decorator import LoggerDecorator
        logger = LoggerDecorator(protocol)
    except ImportError:
        # Dummy logger implementation
        class DummyLogger:
            def __init__(self):
                self.well_volumes = {}  # Placeholder for well volumes
                self.well_capacity = {}  # Placeholder for well capacities
            def wrap_instrument(self, instrument): return instrument
            def wrap_module(self, module): return module
            def log_action(self, action: str): pass
            def log_info(self, info_message: str): pass
            def get_tip_usage(self): return 0
        logger = DummyLogger()

def run(protocol):
    # Ensure the logger is initialized
    initialize_logger(protocol)

    # Initialize well capacities and volumes dynamically
    def update_well_tracking(labware, capacity, initial_volume=0, overrides=None):
        """
        Utility to update well tracking for labware.
        Args:
            labware: The labware object.
            capacity: Default capacity for wells.
            initial_volume: Default initial volume for wells.
            overrides: Dictionary of well-specific volumes, e.g., {"A1": 360, "B1": 100}.
        """
        for well in labware.wells():
            well_name = well.well_name
            logger.well_capacity[well] = capacity
            logger.well_volumes[well] = overrides.get(well_name, initial_volume) if overrides else initial_volume
            
    # Labware
    tiprack_20 = protocol.load_labware('opentrons_96_tiprack_20ul', 3)
    tiprack_300 = protocol.load_labware('opentrons_96_tiprack_300ul', 4)
    tiprack_300 = protocol.load_labware('opentrons_96_tiprack_300ul', 6)
    tiprack_300 = protocol.load_labware('opentrons_96_tiprack_300ul', 9)

    reservoir = protocol.load_labware('nest_12_reservoir_15ml', 5)
    plate = protocol.load_labware('corning_96_wellplate_360ul_flat', 2)

    tc_mod = logger.wrap_module(protocol.load_module('thermocycler module' , 7))
    tc_plate = tc_mod.load_labware('4ti0960rig_96_wellplate_200ul')
    mag_mod = logger.wrap_module(protocol.load_module('magnetic module', 1))
    mag_plate = mag_mod.load_labware('4ti0960rig_96_wellplate_200ul')
   
    # Pipettes
    p20 = logger.wrap_instrument(protocol.load_instrument('p20_single_gen2', mount='right', tip_racks=[tiprack_20]))
    p300 = logger.wrap_instrument(protocol.load_instrument('p300_single_gen2', mount='left', tip_racks=[tiprack_300]))

    # Reagent locations in the well-plate
    master_mix_A = plate.wells_by_name()['A1']
    master_mix_T = plate.wells_by_name()['B1']
    master_mix_C = plate.wells_by_name()['C1']
    master_mix_G = plate.wells_by_name()['D1']
    Manganese = plate.wells_by_name()['E1']
    Lib_Aptamers = plate.wells_by_name()['H1']
    R1_Aptamers = plate.wells_by_name()['A2']
    R2_Aptamers = plate.wells_by_name()['B2']
    R3_Aptamers = plate.wells_by_name()['C2']
    R4_Aptamers = plate.wells_by_name()['D2']
    R5_Aptamers = plate.wells_by_name()['E2']
    R6_Aptamers = plate.wells_by_name()['F2']
    SR1_Aptamers = plate.wells_by_name()['A3']
    SR2_Aptamers = plate.wells_by_name()['B3']
    SR3_Aptamers = plate.wells_by_name()['C3']
    SR4_Aptamers = plate.wells_by_name()['D3']
    SR5_Aptamers = plate.wells_by_name()['E3']
    SR6_Aptamers = plate.wells_by_name()['F3']

    # Reagent locations in the reservoir
    water = reservoir.wells_by_name()['A1']
    MP = reservoir.wells_by_name()['A2']
    MB = reservoir.wells_by_name()['A3']
    ethanol = reservoir.wells_by_name()['A4']
    waste = reservoir.wells_by_name()['A12']
    list_rows = ["A", "B", "C", "D", "E", "F", "G", "H"] 

    # sets the starting volumes of wells for the simlogger
    update_well_tracking(
        reservoir,
        capacity=15000,
        initial_volume=15000,
        overrides={"A12": 0}
    )
    update_well_tracking(
        plate,
        capacity=360,
        initial_volume=0,
        overrides={'A1': 360, 'B1': 360, 'C1': 360, 'D1': 360, 'E1': 360, 'H1': 360}
    )
    update_well_tracking(
        tc_plate,
        capacity=200,
        initial_volume=0,
        overrides={}
    )
    update_well_tracking(
        mag_plate,
        capacity=200,
        initial_volume=0,
        overrides={}
    )
    
    # Flow rates
    p300_aspirate_fast = 1.1
    p300_aspirate_slow = 0.43
    p300_dispense_fast = 1.6    # Also use for mixing
    p300_dispense_slow = 0.81
    p20_aspirate_fast = 2.7
    p20_dispense_fast = 4.0     # Also use for mixing
    p20_aspirate_slow = 1.32
    p20_dispense_slow = 2.0

    # Bottom adjustment
    btm_tc = 10

    # Volumes for reagents
    MP_volume = [0, 5, 10, 20]
    MB_volume = 40

    # Library configurations
    library_config = [
        {'high': master_mix_A},  # Library 1: M Atcg
        {'high': master_mix_T},  # Library 2: M aTcg
        {'high': master_mix_C},  # Library 3: M atCg
        {'high': master_mix_G},  # Library 4: M atcG
        {'high': master_mix_A},  # Library 5: m Atcg
        {'high': master_mix_T},  # Library 6: m aTcg
        {'high': master_mix_C},  # Library 7: m atCg
        {'high': master_mix_G}   # Library 8: m atcG
    ]

    # TC column locations
    tc_plate_columns = [
    ['A1', 'B1', 'C1', 'D1', 'E1', 'F1', 'G1', 'H1'], 
    ['A2', 'B2', 'C2', 'D2', 'E2', 'F2', 'G2', 'H2'],  
    ['A3', 'B3', 'C3', 'D3', 'E3', 'F3', 'G3', 'H3'],  
    ['A4', 'B4', 'C4', 'D4', 'E4', 'F4', 'G4', 'H4'],
    ['A5', 'B5', 'C5', 'D5', 'E5', 'F5', 'G5', 'H5'],
    ['A6', 'B6', 'C6', 'D6', 'E6', 'F6', 'G6', 'H6']
    ]

    # Wells for each run
    aspirate_wells = [Lib_Aptamers, SR1_Aptamers]
    dispense_wells = [R1_Aptamers, R2_Aptamers]

     # Number of PCR runs
    pcr_runs = 2  # Adjust this value as needed

    # Iterate over each run
    for run in range(1, pcr_runs + 1):
        # Destination column in the TC plate for the current run
        TC_wells = [tc_plate.wells_by_name()[well] for well in tc_plate_columns[run - 1]]

        # Protocol steps
        # Step 1: Add 5 µL of Aptamers generated from the last run to each well
        tc_mod.open_lid()
        protocol.comment("Adding aptamers to the Thermocycler plate")
        p20.pick_up_tip()
        for TC_well in TC_wells:
            p20.aspirate(5, aspirate_wells[run -1 ], rate = p20_aspirate_fast)
            p20.dispense(5, TC_well.bottom(btm_tc), rate = p20_dispense_fast)
        p20.drop_tip()

        # Step 2: Add 5 µL of Manganese to the first four wells
        protocol.comment("Adding additional Manganese to the first four wells")
        p20.pick_up_tip()
        for TC_well in TC_wells[:4]:
            p20.aspirate(5, Manganese, rate = p20_aspirate_slow)
            p20.dispense(5, TC_well.bottom(btm_tc), rate = p20_dispense_slow)
        p20.drop_tip()

        # Step 3: Add 5 µL of water to the last four wells
        protocol.comment("Adding water to the last four wells")
        p20.pick_up_tip()
        for TC_well in TC_wells[5:8]:
            p20.aspirate(5, water, rate = p20_aspirate_fast)
            p20.dispense(5, TC_well.bottom(btm_tc), rate = p20_dispense_fast)
        p20.drop_tip()

        # Step 4: Add 15 µL of master mix to each well
        for i, config in enumerate(library_config):
            TC_well = TC_wells[i]
            protocol.comment("Adding appropriate master mix to each well")
            p300.pick_up_tip()
            p300.aspirate(15, config['high'], rate = p300_aspirate_slow)
            p300.dispense(15, TC_well.bottom(btm_tc), rate = p300_dispense_slow)
            p300.mix(10, 30, TC_well.bottom(btm_tc), rate = p300_dispense_fast)
            p300.drop_tip()
   
        # Step 5: Close the lid and run the thermocycler
        protocol.comment("Running the thermocycler for PCR")
        tc_mod.close_lid()
        tc_mod.set_lid_temperature(98)

        profile = [
            {'temperature': 98, 'hold_time_seconds': 10},
            {'temperature': 66, 'hold_time_minutes': 0.5},
            {'temperature': 72, 'hold_time_minutes': 0.5}
        ]

        tc_mod.set_block_temperature(98, hold_time_minutes= 0.05, block_max_volume=20)
        tc_mod.execute_profile(steps=profile, repetitions=35, block_max_volume=20)
        tc_mod.set_block_temperature(72, hold_time_minutes= 2, block_max_volume=20)
        tc_mod.set_block_temperature(4)
        tc_mod.open_lid()
        tc_mod.deactivate_lid()

        # Step 6: Combine contents of all TC wells into well Column 2
        protocol.comment("Pooling the resulting aptamers in the 96 wellplate")
        p300.pick_up_tip()
        for TC_well in TC_wells:
            p300.aspirate(20, TC_well.bottom(btm_tc), rate = p300_aspirate_slow)  # Aspirate the contents of each TC well
            p300.dispense(20, dispense_wells[run -1], rate = p300_dispense_slow)  # Dispense into run well
        p300.drop_tip()

        # SELEX selection
        library_volume = 240

        protocol.comment(f"Moving the aptamer Library after PCR {run}º")
        p300.pick_up_tip()
        p300.aspirate(library_volume, plate[f"{list_rows[run-1]}2"])
        p300.dispense(library_volume, plate[f"A{run+6}"])
        p300.drop_tip()

        # Step 1. Add Milk Powder (MP)to the aptamer library.
        for selex_step in range(len(MP_volume)):
            if MP_volume[selex_step] == 0:
                protocol.comment("No Milk Powder added for 1º iteration")
            else:
                p20.pick_up_tip()
                protocol.comment(f"Adding {MP_volume[selex_step]} µl of Milk Powder")
                p20.aspirate(MP_volume[selex_step], MP, rate = p20_aspirate_fast)
                p20.dispense(MP_volume[selex_step], plate[f"{list_rows[selex_step]}{run+6}"], rate = p20_dispense_fast)
                p20.drop_tip()
            
            # Step 2. Add magnetic beads (MB) to the same well.
            
            protocol.comment("Adding Magnetic Beads")
            p300.pick_up_tip()
            p300.aspirate(MB_volume, MB)
            p300.dispense(MB_volume, plate[f"{list_rows[selex_step]}{run+6}"])
            p300.mix(5, 150, plate[f"{list_rows[selex_step]}{run+6}"], rate = p300_dispense_fast)
            p300.drop_tip()
            
            # Step 3. Incubate for 5 min
            protocol.delay(minutes=5, msg="Delaying for 5 minutes...")
            tc_mod.open_lid()

            # Step 4. Transfer the aptamer library + Milk to the mag_plate

            p300.pick_up_tip()
            p300.aspirate(library_volume + MP_volume[selex_step] + MB_volume, plate[f"{list_rows[selex_step]}{run+6}"], rate = p300_aspirate_slow)

            if selex_step == 0:
                # Dispense evenly into 2 wells to avoid overflowing.

                p300.dispense(((library_volume + MP_volume[selex_step] + MB_volume) / 2), mag_plate[f"{list_rows[selex_step*2]}{run*2-1}"], rate = p300_dispense_slow)
                p300.dispense(((library_volume + MP_volume[selex_step] + MB_volume) / 2), mag_plate[f"{list_rows[selex_step*2+1]}{run*2-1}"], rate = p300_dispense_slow)
                p300.drop_tip()

                # Step 5.1 Pull down by activating the magnets. 
                
                protocol.comment("Magnet activation")
                mag_mod.engage(height_from_base=2) 
                protocol.delay(minutes=3, msg="3 min incubation to allow beads to move to magnet")
                
                # Aspirate supernatant of both wells. 
                    
                p300.pick_up_tip()
                p300.aspirate((library_volume + MP_volume[selex_step]) / 2, mag_plate[f"{list_rows[selex_step*2]}{run*2-1}"], rate = p300_aspirate_slow)
                p300.dispense((library_volume + MP_volume[selex_step]) / 2, waste, rate = p300_dispense_fast)
                p300.aspirate((library_volume + MP_volume[selex_step]) / 2, mag_plate[f"{list_rows[selex_step*2+1]}{run*2-1}"], rate = p300_aspirate_slow)
                p300.dispense((library_volume + MP_volume[selex_step]) / 2, waste, rate = p300_dispense_fast)
                p300.drop_tip()

                # Here it will just leave the volume that would account to the magnetic beads

                # The remaining volume should be always 20 in each well
            
                protocol.comment("Magnet deactivation")
                mag_mod.disengage()
            
                # 6.1 Ethanol wash and move to the thermocycler. Then let air dry for 10 min
            
                protocol.comment("Performing Ethanol Wash")
            
                # Here we divide the ethanol wash into the 2 wells where the sample is then merge together in the thermocycler to avoid overflowing
            
                for wash_step in range(2): 
                    p300.pick_up_tip()
                    p300.aspirate(50, ethanol, rate = p300_aspirate_slow)  
                    p300.aspirate(20, ethanol.bottom(20)) # "Aspirate" air gap
                    p300.dispense(20, mag_plate[f"{list_rows[selex_step+wash_step]}{run*2-1}"].bottom(12))
                    p300.dispense(50, mag_plate[f"{list_rows[selex_step+wash_step]}{run*2-1}"]) 
                    p300.mix(5, 50, mag_plate[f"{list_rows[selex_step+wash_step]}{run*2-1}"], rate = p300_dispense_fast)
                    p300.drop_tip()

                # Now we merge everything in the thermocycler

                    p300.pick_up_tip()
                    p300.aspirate(70, mag_plate[f"{list_rows[selex_step*2]}{run*2-1}"]) 
                    p300.aspirate(20, mag_plate[f"{list_rows[selex_step*2]}{run*2-1}"].bottom(12))
                    p300.dispense(20, tc_plate[f"{list_rows[selex_step]}{run+6}"].bottom(16))
                    p300.dispense(70, tc_plate[f"{list_rows[selex_step]}{run+6}"].bottom(btm_tc)) 
                    p300.drop_tip()

                protocol.comment("Samples merged in thermocycler well")

                # Now it won't overflow with this first step of SELEX

            else:
                # For the the following SELEX iterations after the first one, we don't have an overflowing problem because the library was diluted to 45 µl
                # reminder of last step: p300.aspirate(library_volume + MP_volume[selex_step] + MB_volume, plate[f"{list_rows[selex_step]}{run+6}"], rate = p300_aspirate_slow)
                p300.dispense(library_volume + MP_volume[selex_step] + MB_volume, mag_plate[f"{list_rows[selex_step*2]}{run*2-1}"], rate = p300_dispense_slow)
                p300.drop_tip()
                
                # 5.2 Pull down by activating the magnets. 
                
                protocol.comment("Magnet activation")
                mag_mod.engage(height_from_base=2) 
                protocol.delay(minutes=3, msg="3 min incubation to allow beads to move to magnet")
                
                # Aspirate supernatant of the well.
                    
                p300.pick_up_tip()
                p300.aspirate(library_volume + MP_volume[selex_step], mag_plate[f"{list_rows[selex_step*2]}{run*2-1}"], rate = p300_aspirate_slow)
                p300.dispense(library_volume + MP_volume[selex_step], waste, rate = p300_dispense_fast)
                p300.drop_tip()

                # Here it will just leave the volume that would account to the magnetic beads
            
                protocol.comment("Magnet deactivation")
                mag_mod.disengage()
            
                # 6.2 Ethanol wash and move to the thermocycler. Then let air dry for 10 min
            
                protocol.comment("Performing Ethanol Wash")
                
                p300.pick_up_tip()
                p300.aspirate(50, ethanol, rate = p300_aspirate_slow) 
                p300.aspirate(20, ethanol.bottom(20)) # "Aspirate" air gap
                p300.dispense(20, mag_plate[f"{list_rows[selex_step*2]}{run*2-1}"].bottom(12))
                p300.dispense(50, mag_plate[f"{list_rows[selex_step*2]}{run*2-1}"]) 
                p300.mix(5, 30, mag_plate[f"{list_rows[selex_step*2]}{run*2-1}"], rate = p300_dispense_fast)
                p300.drop_tip()

                p300.pick_up_tip()
                p300.aspirate(70, mag_plate[f"{list_rows[selex_step*2]}{run*2-1}"]) # We need to make sure we take everything in here
                p300.aspirate(20, mag_plate[f"{list_rows[selex_step*2]}{run*2-1}"].bottom(12))
                p300.dispense(20, tc_plate[f"{list_rows[selex_step]}{run+6}"].bottom(16))
                p300.dispense(70, tc_plate[f"{list_rows[selex_step]}{run+6}"].bottom(btm_tc)) 
                p300.drop_tip()

                protocol.comment("Sample moved into the thermocycler well")
            

            protocol.comment("Heat to 95 ºC")
            
            tc_mod.close_lid()
            
            tc_mod.set_block_temperature(95, hold_time_minutes= 1, block_max_volume=100)
            tc_mod.set_block_temperature(4)
            tc_mod.open_lid()
            tc_mod.deactivate_lid()
            protocol.delay(minutes=10, msg="Air dry the pellet for 10mins at RT")

            # 7. Re-suspend with mQ water and incubate for 5 minutes to elute the sample off the beads.
            
            protocol.comment("Adding elution buffer")
            p300.pick_up_tip()
            p300.aspirate(47, water. bottom(7), rate = p300_aspirate_fast)
            p300.dispense(47, tc_plate[f"{list_rows[selex_step]}{run+6}"].bottom(12), rate = p300_dispense_fast)
            p300.mix(5, 30, tc_plate[f"{list_rows[selex_step]}{run+6}"].bottom(12), rate = p300_dispense_fast)
            
            p300.aspirate(47, tc_plate[f"{list_rows[selex_step]}{run+6}"].bottom(12), rate = p300_aspirate_fast)
            p300.dispense(47, mag_plate[f"{list_rows[selex_step*2]}{run*2}"], rate = p300_dispense_fast)
            p300.drop_tip()
            
            
            # 8. Re-engage the magnetic plate, incubate for 5 min to allow the beads to interact with the magnets 
            # and then take the supernatant containing the mQ water with the selected aptamers into a destination well. 
            
            mag_mod.engage(height_from_base=2)
            protocol.delay(minutes=5, msg="Incubate at RT for 5 mins to allow beads to move to magnet")
            
            p300.pick_up_tip()
            p300.aspirate(45, mag_plate[f"{list_rows[selex_step*2]}{run*2}"].bottom(2), rate = p300_aspirate_slow)
            p300.dispense(45, plate[f"{list_rows[selex_step+1]}{run+6}"])
            p300.drop_tip()

            library_volume = 45

            protocol.comment(f" End of {selex_step+1}° SELEX selection")

            if selex_step+1 == len(MP_volume):
                p300.pick_up_tip()
                p300.aspirate(45, plate[f"{list_rows[selex_step+1]}{run+6}"])
                p300.dispense(45, plate[f"{list_rows[run]}{3}"])
                p300.drop_tip()

