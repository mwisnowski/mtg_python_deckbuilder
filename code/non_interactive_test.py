from deck_builder.builder import DeckBuilder

"""Non-interactive harness.

Features:
  - Script commander selection.
  - Script primary / optional secondary / tertiary tags.
  - Apply bracket & accept default ideal counts.
  - Invoke multi-theme creature addition if available (fallback to primary-only).

Use run(..., secondary_choice=2, tertiary_choice=3, use_multi_theme=True) to exercise multi-theme logic.
Indices correspond to the numbered tag list presented during interaction.
"""

def run(
    command_name: str = "Finneas, Ace Archer",
    add_creatures: bool = True,
    use_multi_theme: bool = True,
    primary_choice: int = 11,
    secondary_choice: int | None = None,
    tertiary_choice: int | None = None,
    add_lands: bool = True,
    fetch_count: int | None = 3,
    dual_count: int | None = None,
    triple_count: int | None = None,
    utility_count: int | None = None,
):
    scripted_inputs: list[str] = []
    # Commander query & selection
    scripted_inputs.append(command_name)        # initial query
    scripted_inputs.append("1")                # choose first search match to inspect
    scripted_inputs.append("y")                # confirm commander
    # Primary tag selection
    scripted_inputs.append(str(primary_choice))
    # Secondary tag selection or stop (0)
    if secondary_choice is not None:
        scripted_inputs.append(str(secondary_choice))
        # Tertiary tag selection or stop (0)
        if tertiary_choice is not None:
            scripted_inputs.append(str(tertiary_choice))
        else:
            scripted_inputs.append("0")
    else:
        scripted_inputs.append("0")  # stop at primary
    # Bracket (meta power / style) selection; keeping existing scripted value
    scripted_inputs.append("5")
    # Ideal count prompts (press Enter for defaults)
    for _ in range(8):
        scripted_inputs.append("")

    def scripted_input(prompt: str) -> str:
        if scripted_inputs:
            return scripted_inputs.pop(0)
        raise RuntimeError("Ran out of scripted inputs for prompt: " + prompt)

    builder = DeckBuilder(input_func=scripted_input)
    builder.run_initial_setup()
    builder.run_deck_build_step1()
    builder.run_deck_build_step2()
    
    # Land sequence (optional)
    if add_lands:
        if hasattr(builder, 'run_land_step1'):
            builder.run_land_step1()  # Basics / initial
        if hasattr(builder, 'run_land_step2'):
            builder.run_land_step2()  # Utility basics / rebalancing
        if hasattr(builder, 'run_land_step3'):
            builder.run_land_step3()  # Kindred lands if applicable
        if hasattr(builder, 'run_land_step4'):
            builder.run_land_step4(requested_count=fetch_count)
        if hasattr(builder, 'run_land_step5'):
            builder.run_land_step5(requested_count=dual_count)
        if hasattr(builder, 'run_land_step6'):
            builder.run_land_step6(requested_count=triple_count)
        if hasattr(builder, 'run_land_step7'):
            builder.run_land_step7(requested_count=utility_count)
        if hasattr(builder, 'run_land_step8'):
            builder.run_land_step8()

    if add_creatures:
        builder.add_creatures()
        

    builder.print_card_library()
    builder.post_spell_land_adjust()
    return builder

if __name__ == "__main__":
    run()
