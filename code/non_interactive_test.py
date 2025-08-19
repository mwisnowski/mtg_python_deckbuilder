from deck_builder.builder import DeckBuilder

# Non-interactive harness: chooses specified commander, first tag, first bracket, accepts defaults

def run(command_name: str = "Rocco, Street Chef"):
    scripted_inputs = []
    # Commander query
    scripted_inputs.append(command_name)  # initial query
    # After showing matches, choose first candidate (index 1)
    scripted_inputs.append("1")  # select first candidate to inspect
    scripted_inputs.append("y")  # confirm commander
    # Tag selection: choose eleventh tag as primary
    scripted_inputs.append("11")
    # Stop after primary (secondary prompt enters 1)
    scripted_inputs.append("1")
    # Stop after primary (tertiary prompt enters 0)
    scripted_inputs.append("0")
    # Bracket selection: choose 3 (Typical Casual mid default) else 2 maybe; pick 3
    scripted_inputs.append("5")
    # Ideal counts prompts (8 prompts) -> press Enter (empty) to accept defaults
    for _ in range(8):
        scripted_inputs.append("")

    def scripted_input(prompt: str) -> str:
        if scripted_inputs:
            return scripted_inputs.pop(0)
        raise RuntimeError("Ran out of scripted inputs for prompt: " + prompt)

    b = DeckBuilder(input_func=scripted_input)
    b.run_initial_setup()
    b.run_deck_build_step1()
    b.run_deck_build_step2()
    b.run_land_step1()
    b.run_land_step2()
    # Land Step 3: Kindred lands (if applicable)
    b.run_land_step3()
    # Land Step 4: Fetch lands (request exactly 3)
    b.run_land_step4(requested_count=3)
    # Land Step 5: Dual lands (use default desired)
    b.run_land_step5()
    # Land Step 6: Triple lands (use default desired 1-2)
    b.run_land_step6()
    # Land Step 7: Misc utility lands
    b.run_land_step7()
    # Land Step 8: Optimize tapped lands
    b.run_land_step8()
    b.print_card_library()
    # Run post-spell (currently just analysis since spells not added in this harness)
    b.post_spell_land_adjust()
    return b

if __name__ == "__main__":
    run()
