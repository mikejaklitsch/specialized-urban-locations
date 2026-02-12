# Dynamic Texture Path Test Results

Baseline: `location_rank_icon` in `map_markers.gui` with vanilla `[Location.GetRankIcon]` — displays correctly.

## Test 1: Static texture path
```
texture = "gfx/interface/mapitems/red_town.dds"
```
**WORKS** — red town icon visible on all locations.

## Test 2: Select_CString (simple bool, no variables)
```
texture = "[Select_CString(Location.IsCapital, 'gfx/interface/mapitems/red_capital_town.dds', 'gfx/interface/mapitems/red_town.dds')]"
```
**FAILS** — icon locations empty, nothing renders. No errors in log. Select_CString silently fails for texture property.

## Test 3: Concatenate
```
texture = "[Concatenate('gfx/interface/mapitems/', 'red_town.dds')]"
```
**FAILS** — icons do not appear. Identical to test 2. These errors ONLY occur with this test, never otherwise:
```
Event target link 'variable_map' returned an unset scope — sul_gdp_scaling.txt:13
Value of wrong type in sul_pop_demands.txt (multiple lines). Got value of type 'none'
Failed to fetch key for 'sul_gdp_pc' map due to not being set — sul_gdp_scaling.txt:13
```
Concatenate texture somehow triggers cascading script errors in unrelated systems.

## Test 4: Variable-based Select_CString (float, base game pattern)
```
texture = "[Select_CString(EqualTo_float(FixedPointToFloat(Location.MakeScope.GetVariable('sul_spec_type').GetValue), '(float)1.0'), 'gfx/interface/mapitems/red_town.dds', 'gfx/interface/mapitems/green_town.dds')]"
```
**FAILS** — identical to test 3 (Concatenate). Icons do not appear.

## Test 5: Variable-based Select_CString (int32, our original)
```
texture = "[Select_CString(EqualTo_int32(FixedPointToInt(Location.MakeScope.GetVariable('sul_spec_type').GetValue), '(int32)1'), 'gfx/interface/mapitems/red_town.dds', 'gfx/interface/mapitems/green_town.dds')]"
```
**FAILS** — identical to tests 2-4. Icons do not appear.

## Test 6: Location.Custom → full static path (no nesting)
```
texture = "[Location.Custom('sul_test_texture')]"
# customizable_localization resolves to literal "gfx/interface/mapitems/red_town.dds"
```
**PENDING**

## Test 7: CityMarker.GetLocation.Custom → full static path (no nesting)
```
texture = "[CityMarker.GetLocation.Custom('sul_test_texture')]"
# customizable_localization resolves to literal "gfx/interface/mapitems/red_town.dds"
```
**PENDING**

## Test 8: Location.Custom → loc string with nested Location.Custom
```
texture = "[Location.Custom('sul_town_texture')]"
# loc string: "gfx/interface/mapitems/[Location.Custom('sul_spec_color')]_town.dds"
```
**PENDING**

## Test 9: Location.Custom → loc string with nested CityMarker.GetLocation.Custom
```
texture = "[Location.Custom('sul_town_texture')]"
# loc string: "gfx/interface/mapitems/[CityMarker.GetLocation.Custom('sul_spec_color')]_town.dds"
```
**PENDING**

## Test 10: CityMarker.GetLocation.Custom → loc string with nested Location.Custom
```
texture = "[CityMarker.GetLocation.Custom('sul_town_texture')]"
# loc string: "gfx/interface/mapitems/[Location.Custom('sul_spec_color')]_town.dds"
```
**PENDING**

## Test 11: CityMarker.GetLocation.Custom → loc string with nested CityMarker.GetLocation.Custom
```
texture = "[CityMarker.GetLocation.Custom('sul_town_texture')]"
# loc string: "gfx/interface/mapitems/[CityMarker.GetLocation.Custom('sul_spec_color')]_town.dds"
```
**PENDING**

## Test 12: Spritesheet + dynamic frame
**PENDING**

## Test 13: Visibility-gated static icons
**PENDING**
