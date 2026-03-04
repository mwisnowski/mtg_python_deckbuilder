# Build.py Splitting Strategy

**Status**: Planning (R9 M1)  
**Created**: 2026-02-20

## Current State

[code/web/routes/build.py](../../code/web/routes/build.py) is **5,740 lines** with 40+ route endpoints.

## Analysis of Route Groups

Based on route path analysis, the file can be split into these logical modules:

### 1. **Validation Routes** (~200 lines)
- `/build/validate/card` - Card name validation
- `/build/validate/cards` - Bulk card validation
- `/build/validate/commander` - Commander validation
- Utility functions: `_available_cards()`, `warm_validation_name_cache()`

**New module**: `code/web/routes/build_validation.py`

### 2. **Include/Exclude Routes** (~300 lines)
- `/build/must-haves/toggle` - Toggle include/exclude feature
- Include/exclude card management
- Related utilities and form handlers

**New module**: `code/web/routes/build_include_exclude.py`

### 3. **Partner/Background Routes** (~400 lines)
- `/build/partner/preview` - Partner commander preview
- `/build/partner/*` - Partner selection flows
- Background commander handling

**New module**: `code/web/routes/build_partners.py`

### 4. **Multi-copy Routes** (~300 lines)
- `/build/multicopy/check` - Multi-copy detection
- `/build/multicopy/save` - Save multi-copy preferences
- `/build/new/multicopy` - Multi-copy wizard step

**New module**: `code/web/routes/build_multicopy.py`

### 5. **Theme Management Routes** (~400 lines)
- `/build/themes/add` - Add theme
- `/build/themes/remove` - Remove theme
- `/build/themes/choose` - Choose themes
- `/build/themes/mode` - Theme matching mode

**New module**: `code/web/routes/build_themes.py`

### 6. **Step-based Wizard Routes** (~1,500 lines)
- `/build/step1` - Commander selection (GET/POST)
- `/build/step2` - Theme selection
- `/build/step3` - Ideals configuration
- `/build/step4` - Owned cards
- `/build/step5` - Final build
- `/build/step*/*` - Related step handlers

**New module**: `code/web/routes/build_wizard.py`

### 7. **New Build Routes** (~1,200 lines)
- `/build/new` - Start new build (GET/POST)
- `/build/new/candidates` - Commander candidates
- `/build/new/inspect` - Inspect commander
- `/build/new/toggle-skip` - Skip wizard steps
- Single-page build flow (non-wizard)

**New module**: `code/web/routes/build_new.py`

### 8. **Permalink/Lock Routes** (~400 lines)
- `/build/permalink` - Generate permalink
- `/build/from` - Restore from permalink
- `/build/locks/*` - Card lock management
- State serialization/deserialization

**New module**: `code/web/routes/build_permalinks.py`

### 9. **Deck List Routes** (~300 lines)
- `/build/view/*` - View completed decks
- `/build/list` - List saved decks
- Deck export and display

**New module**: `code/web/routes/build_decks.py`

### 10. **Shared Utilities** (~300 lines)
- Common helper functions
- Response builders (migrate to `utils/responses.py`)
- Session utilities (migrate to `services/`)

**New module**: `code/web/routes/build_utils.py` (temporary, will merge into services)

## Migration Strategy

### Phase 1: Extract Validation (Low Risk)
1. Create `build_validation.py`
2. Move validation routes and utilities
3. Test validation endpoints
4. Update imports in main build.py

### Phase 2: Extract Simple Modules (Low-Medium Risk)
1. Multi-copy routes → `build_multicopy.py`
2. Include/Exclude routes → `build_include_exclude.py`
3. Theme routes → `build_themes.py`
4. Partner routes → `build_partners.py`

### Phase 3: Extract Complex Wizard (Medium Risk)
1. Step-based wizard → `build_wizard.py`
2. Preserve session management carefully
3. Extensive testing required

### Phase 4: Extract New Build Flow (Medium-High Risk)
1. Single-page build → `build_new.py`
2. Test all build flows thoroughly

### Phase 5: Extract Permalinks and Decks (Low Risk)
1. Permalink/Lock routes → `build_permalinks.py`
2. Deck list routes → `build_decks.py`

### Phase 6: Cleanup (Low Risk)
1. Move utilities to proper locations
2. Remove `build_utils.py`
3. Update all imports
4. Final testing

## Import Strategy

Each new module will have a router that gets included in the main build router:

```python
# code/web/routes/build.py (main file, reduced to ~500 lines)
from fastapi import APIRouter
from . import (
    build_validation,
    build_include_exclude,
    build_partners,
    build_multicopy,
    build_themes,
    build_wizard,
    build_new,
    build_permalinks,
    build_decks,
)

router = APIRouter(prefix="/build", tags=["build"])

# Include sub-routers
router.include_router(build_validation.router)
router.include_router(build_include_exclude.router)
router.include_router(build_partners.router)
router.include_router(build_multicopy.router)
router.include_router(build_themes.router)
router.include_router(build_wizard.router)
router.include_router(build_new.router)
router.include_router(build_permalinks.router)
router.include_router(build_decks.router)
```

## Testing Plan

For each module extracted:
1. Run existing test suite
2. Manual testing of affected routes
3. Integration tests for cross-module interactions
4. Smoke test full build flow (wizard + single-page)

## Risks

**High Risk:**
- Breaking session state management across modules
- Import circular dependencies
- Lost functionality in split

**Mitigations:**
- Extract one module at a time
- Full test suite after each module
- Careful session/state handling
- Keep shared utilities accessible

**Medium Risk:**
- Performance regression from additional imports
- HTMX/template path issues

**Mitigations:**
- Profile before/after
- Update template paths carefully
- Test HTMX partials thoroughly

## Success Criteria

- [ ] All 9 modules created and tested
- [ ] Main build.py reduced to <500 lines
- [ ] All tests passing
- [ ] No functionality lost
- [ ] Documentation updated
- [ ] Import structure clean

---

**Next Steps:**
1. Start with Phase 1 (Validation routes - low risk)
2. Create `build_validation.py`
3. Test thoroughly
4. Proceed to Phase 2

**Last Updated**: 2026-02-20  
**Roadmap**: R9 M1 - Route Handler Standardization
