# Brand assets

One mark: an isometric book with a wrench, drawn in navy. Images are PNG, plus one ICO favicon and one JSON manifest snippet.

Brand navy is `#001A46` (RGB 0, 26, 70). It is the background of every opaque export and the text colour of every navy-on-transparent one.

## Colourways

Every wordmark and lockup comes in three, named by what colour the mark is and what it sits on:

- `navy-on-transparent`: for light backgrounds. Used in the README in light theme.
- `white-on-transparent`: for dark backgrounds. Used in the README in dark theme.
- `white-on-navy`: opaque, self-contained, for anywhere the background cannot be controlled.

A `master` file is the export at its native size; the `NNNNw` files are resized to that width.

## Folders

- `icon/`: the mark alone. `circle` for avatars and profile images, `square` for a hard-edged tile, `square-rounded` for app-icon style use. The 1254 px circle is the largest export.
- `wordmark/`: the name alone, in the three colourways.
- `lockup-horizontal/`: icon beside the name. The README header uses the 1200w transparent pair.
- `lockup-stacked/`: icon above the name.
- `social/icon/` and `social/wordmark/`: ready-made cards at the sizes the platforms want. `github-social-preview-1280x640.png` is the one to upload under the repository's Settings, Social preview. The wordmark version is in use.
- `platform/web/`: favicons, Apple touch icon, PWA icons and a manifest snippet, for a documentation site if one is ever built. `pwa-icon-512.png` is the same image as `icon/icon-square-rounded-512.png`, kept here so the manifest snippet works as shipped.
- `platform/android/`: adaptive icon layers and a monochrome variant, for the same reason.

Five byte-identical duplicates from the original pack were dropped: the circle avatar copies of the circle master, the Apple and Google Play icons, which were the rounded square under other names, and the loose `eBook-Metamend-logo-rgb.png`, which was the 1254 px circle.

## Name

The wordmark reads `eBook-Metamend` with a hyphen, matching the repository slug. In prose the project is `eBook Metamend` with a space. Both are correct in their place.
