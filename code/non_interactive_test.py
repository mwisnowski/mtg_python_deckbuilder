from __future__ import annotations

from typing import List, Optional

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
    command_name: str = "Pantlaza",
    add_creatures: bool = True,
    add_non_creature_spells: bool = True,
    # Fine-grained toggles (used only if add_non_creature_spells is False)
    add_ramp: bool = True,
    add_removal: bool = True,
    add_wipes: bool = True,
    add_card_advantage: bool = True,
    add_protection: bool = True,
    use_multi_theme: bool = True,
    primary_choice: int = 2,
    secondary_choice: Optional[int] = 2,
    tertiary_choice: Optional[int] = 2,
    add_lands: bool = True,
    fetch_count: Optional[int] = 3,
    dual_count: Optional[int] = None,
    triple_count: Optional[int] = None,
    utility_count: Optional[int] = None,
    seed: Optional[int] = None,
) -> DeckBuilder:
    """Run a scripted non-interactive deck build and return the DeckBuilder instance.

    Integer parameters (primary_choice, secondary_choice, tertiary_choice) correspond to the
    numeric indices shown during interactive tag selection. Pass None to omit secondary/tertiary.
    Optional counts (fetch_count, dual_count, triple_count, utility_count) constrain land steps.
    seed: optional deterministic RNG seed for reproducible builds.
    """
    scripted_inputs: List[str] = []
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
    scripted_inputs.append("3")
    # Ideal count prompts (press Enter for defaults)
    for _ in range(8):
        scripted_inputs.append("")

    def scripted_input(prompt: str) -> str:
        if scripted_inputs:
            return scripted_inputs.pop(0)
        raise RuntimeError("Ran out of scripted inputs for prompt: " + prompt)

    builder = DeckBuilder(input_func=scripted_input, seed=seed)
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
    # Non-creature spell categories (ramp / removal / wipes / draw / protection)
    if add_non_creature_spells and hasattr(builder, 'add_non_creature_spells'):
        builder.add_non_creature_spells()
    else:
        # Allow selective invocation if orchestrator not desired
        if add_ramp and hasattr(builder, 'add_ramp'):
            builder.add_ramp()
        if add_removal and hasattr(builder, 'add_removal'):
            builder.add_removal()
        if add_wipes and hasattr(builder, 'add_board_wipes'):
            builder.add_board_wipes()
        if add_card_advantage and hasattr(builder, 'add_card_advantage'):
            builder.add_card_advantage()
        if add_protection and hasattr(builder, 'add_protection'):
            builder.add_protection()
        

    # Suppress verbose library print in non-interactive run since CSV export is produced.
    # builder.print_card_library()
    builder.post_spell_land_adjust()
    # Export decklist CSV (commander first word + date)
    if hasattr(builder, 'export_decklist_csv'):
        builder.export_decklist_csv()
    return builder

if __name__ == "__main__":
    run()
