from deck_builder import builder_utils as bu


class DummyBuilder:
    def __init__(self, color_identity, selected_tags=None, commander_dict=None):
        self.color_identity = color_identity
        self.selected_tags = selected_tags or []
        self.commander_dict = commander_dict or {"Themes": []}


def test_detector_dragon_approach_minimal():
    b = DummyBuilder(color_identity=['R'], selected_tags=['Spellslinger'])
    results = bu.detect_viable_multi_copy_archetypes(b)
    ids = [r['id'] for r in results]
    assert 'dragons_approach' in ids
    da = next(r for r in results if r['id']=='dragons_approach')
    assert da['name'] == "Dragon's Approach"
    assert da['type_hint'] == 'noncreature'
    assert da['default_count'] == 25


def test_detector_exclusive_rats_only_one():
    b = DummyBuilder(color_identity=['B'], selected_tags=['rats','aristocrats'])
    results = bu.detect_viable_multi_copy_archetypes(b)
    rat_ids = [r['id'] for r in results if r.get('exclusive_group')=='rats']
    # Detector should keep only one rats archetype in the ranked output
    assert len(rat_ids) == 1
    assert rat_ids[0] in ('relentless_rats','rat_colony')


def test_detector_color_gate_blocks():
    b = DummyBuilder(color_identity=['G'], selected_tags=['Spellslinger'])
    results = bu.detect_viable_multi_copy_archetypes(b)
    ids = [r['id'] for r in results]
    # DA is red, shouldn't appear in mono-G
    assert 'dragons_approach' not in ids
