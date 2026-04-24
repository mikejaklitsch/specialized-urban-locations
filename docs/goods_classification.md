# Goods Classification: Extraction vs Production

All goods classified for the development tradeoff system.
**Extraction** goods get output bonuses at low development, penalties at high.
**Production** goods get output penalties at low development, bonuses at high.

## Global Classification

### Extraction Goods (raw materials — benefit from low development)

| Good | Method | Food | Notes |
|------|--------|------|-------|
| wheat | farming | 8.0 | staple grain |
| rice | farming | 10.0 | staple grain |
| millet | farming | 5.0 | staple grain |
| maize | farming | 8.0 | staple grain |
| potato | farming | 8.0 | staple tuber |
| legumes | farming | 5.0 | staple pulse |
| olives | farming | 4.0 | oil crop |
| fruit | farming | 4.0 | perishable |
| livestock | farming | 8.0 | pastoral |
| horses | farming | — | pastoral/military |
| fiber_crops | farming | — | textile raw |
| cotton | farming | — | textile raw |
| silk | farming | — | luxury textile raw |
| wool | gathering | 5.0 | textile raw |
| fish | gathering | 5.0 | coastal/river |
| wild_game | hunting | 3.5 | forest meat |
| fur | hunting | 2.0 | forest luxury |
| ivory | hunting | — | luxury |
| beeswax | farming | 2.5 | forest product |
| lumber | forestry | — | universal raw |
| iron | mining | — | base metal |
| copper | mining | — | base metal |
| tin | mining | — | base metal |
| lead | mining | — | base metal |
| coal | mining | — | fuel |
| stone | mining | — | building material |
| marble | mining | — | luxury stone |
| goods_gold | mining | — | precious metal |
| silver | mining | — | precious metal |
| gems | mining | — | precious stones |
| alum | mining | — | chemical |
| mercury | mining | — | chemical |
| salt | gathering | — | mineral/preservative |
| sand | gathering | — | raw material |
| clay | gathering | — | raw material |
| amber | gathering | — | luxury natural |
| pearls | gathering | — | luxury natural |
| saltpeter | gathering | — | military raw |
| medicaments | gathering | — | pharmaceutical |
| wine | farming | — | processed agricultural |
| tea | farming | — | plantation crop |
| coffee | farming | — | plantation crop |
| cocoa | farming | — | plantation crop |
| sugar | farming | — | plantation crop |
| tobacco | farming | — | plantation crop |
| saffron | farming | — | luxury spice |
| pepper | farming | — | spice |
| cloves | farming | — | spice |
| chili | farming | — | spice |
| incense | farming | — | luxury aromatic |
| dyes | farming | — | textile chemical |

### Production Goods (manufactured — benefit from high development)

| Good | Primary Spec | Notes |
|------|-------------|-------|
| cloth | commercial | basic textile |
| fine_cloth | commercial | luxury textile |
| leather | farming/woodland | shared: tanning |
| tools | mining | metalwork |
| steel | mining | refined metal |
| weaponry | mining | military craft |
| firearms | mining | military craft |
| cannons | mining | military craft |
| jewelry | mining | luxury craft |
| glass | gathering | silicate craft |
| pottery | gathering | ceramic craft |
| porcelain | gathering | luxury ceramic |
| paper | woodland | pulp product |
| books | commercial | printed product |
| furniture | woodland | carpentry |
| tar | woodland | forest byproduct |
| naval_supplies | commercial | composite |
| beer | farming | brewed beverage |
| liquor | farming | distilled beverage |
| lacquerware | woodland | decorative craft |
| masonry | mining | building material |
| slaves_goods | — | special, excluded |
| provisions | — | mod good, excluded |

## Per-Specialization Breakdown

### Mining (Type 1)
**Extraction:** iron, copper, tin, lead, coal, stone, marble, goods_gold, silver, gems, alum, mercury
**Production:** tools, steel, weaponry, firearms, cannons, jewelry, masonry

### Farming (Type 2)
**Extraction:** wheat, rice, millet, maize, potato, legumes, olives, fruit, livestock, horses, fiber_crops, cotton, silk, wine, tea, coffee, cocoa, sugar, tobacco, saffron, pepper, cloves, chili, beeswax, incense, dyes
**Production:** beer, liquor, leather

### Gathering (Type 3)
**Extraction:** fish, wool, clay, sand, salt, medicaments, pearls, amber, saltpeter
**Production:** glass, pottery, porcelain, saltpeter (crossover: raw AND refined)

### Woodland (Type 4)
**Extraction:** lumber, wild_game, fur, ivory, beeswax, incense, dyes
**Production:** paper, furniture, tar, lacquerware, leather

### Commercial (Type 5)
**Extraction:** (none — commercial has no resource requirement)
**Production:** cloth, fine_cloth, books, naval_supplies

## Crossover Goods
- **leather**: farming (livestock/hides) + woodland (fur/game)
- **saltpeter**: gathering (raw extraction) + gathering (refined production)
- **beeswax**: farming method but woodland specialization eligible
- **incense**: farming method but woodland specialization eligible
- **dyes**: farming method but woodland specialization eligible
