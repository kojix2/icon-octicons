# icon-octicons

[Octicons](https://github.com/primer/octicons) as 774 pre-rendered `CrImage` constants for Crystal. Icons retain their source dimensions, including non-square logos.

```yaml
dependencies:
  icon-octicons:
    github: kojix2/icon-octicons
```

```crystal
require "icon-octicons"

icon = Icon::Octicons::Heart16
```

Names follow the SVG filenames. Use `require "icon-octicons/16"` to load only one size. PNG data lives in `src/data/*.tsv` and is loaded by a Crystal macro. Constants are shared, mutable images; copy before editing.

## Regenerate

Requires Python 3, librsvg, Cairo, and an upstream ZIP from the project linked above.

```bash
python3 scripts/generate.py /path/to/octicons.zip
python3 scripts/generate.py /path/to/octicons.zip --check
```

If upstream adds a new size, add its `src/<size>.cr` wrapper and require it from `src/icon-octicons.cr`.

MIT: [shard](LICENSE), [upstream icons](LICENSE.octicons).
