# synSPORT

Synthetic data generation applied to sport. The website connects the sport framework to a defined judo question: estimating next-day body mass after official weigh-in.

The initial release contains **Framework** and **Objective**. It presents a scroll narrative and complete chapters with citations, equations, figures and readable R code. It describes the research approach; the conceptual graphics do not contain fitted predictions.

## Run locally

Install Node.js 24 LTS, then run these commands in the `synSPORT` folder:

```sh
npm ci
npm run dev
```

Open **http://127.0.0.1:5173/synSPORT/**. Vite prints the address if that port is already occupied.

To inspect the production build:

```sh
npm run build
npm run check:build
npm run preview
```

Open **http://127.0.0.1:4173/synSPORT/**. Stop either server with `Ctrl+C`.

## Check changes

Install the test browser once, then run the interaction checks:

```sh
npx playwright install chromium
npm run build
npm run check:build
npm test
```

The tests cover desktop, mobile and reduced motion. They check loading, scroll access, navigation, reading panels, appearance, keyboard dismissal and browser errors. Failed checks retain screenshots and traces in ignored test-output folders.

## Source content

`dev/` is local research material and is ignored by Git. The website and its Actions workflow build without that folder, R or the source workbooks.

| Location | Purpose |
| --- | --- |
| `index.html` | The connected narrative and its visual scenes. |
| `src/` | Opening, scrolling, navigation, reading panels and appearance. |
| `content/chapters.json` | Prepared full chapters and source hashes. |
| `public/chapters/` | Standalone chapters for reading and sharing. |
| `public/figures/` | Final Framework and Objective diagrams. |
| `public/media/` | Opening illustration, adapted footage and credits. |
| `public/fonts/` | Local Roboto fonts and their license. |
| `scripts/publish-content.py` | Local preparation of publication content. |
| `.github/workflows/deploy.yml` | Build, test, publish and live verification. |

To refresh the complete chapters after editing the final research sources, keep these files locally:

- `dev/frameworkJD.Rmd` and `dev/objectiveJD.Rmd`
- `dev/bibliography.bib`
- Their diagrams in `dev/figures/`
- `dev/data/judo/judo.xlsx` and `judoDIC.xlsx`

Install Python 3.10+ and Pandoc 3+, then run:

```sh
npm run content
npm run build
npm run check:build
npm test
```

The publication script reads the workbooks only for aggregate counts and measurement definitions. It does not execute R, save a workbook or publish raw athlete rows. It preserves chapter text, citations, mathematics and code while recording source checksums. Review any corresponding narrative changes in `index.html` when the scientific objective changes.

## Publish

GitHub Pages uses **GitHub Actions** in `paulYRP/synSPORT`. The Vite base is `/synSPORT/`.

1. Commit the production changes and push `main`.
2. Open the repository's **Actions** tab and select **Check and publish website** for that commit.
3. The workflow installs locked dependencies, builds the site, validates deployment files and runs browser checks.
4. A successful build is uploaded as a Pages artifact. The deployment job publishes that exact artifact.
5. The live-check job verifies the published chapters and media.

Pull requests run checks without deploying. A manual workflow run on `main` can rebuild and publish the current revision. Only `dist/` is uploaded; `dev/`, workbooks, development files and test recordings are excluded.

Live address: **https://paulyrp.github.io/synSPORT/**

## Online review

| Action | What to verify |
| --- | --- |
| Open the live address in a new tab. | The loading belt gives way to the judoka. Scrolling reveals synSPORT. |
| Scroll forward and backward. | The recorded movement and chapter visuals follow the direction of travel. |
| Open the menu. | Home, Framework and Objective reach their sections. Escape closes the menu. |
| Read each full chapter. | Figures, equations, references and code are readable. Closing returns to the narrative. |
| Open `#objective` directly and refresh. | The Objective section is accessible through a shared link. |
| Follow a chapter citation or open a diagram. | The reference is found and the diagram can be inspected at full size. |
| Use a phone or reduced-motion setting. | The same scientific sequence remains readable. |
| Switch appearance. | Light and dark modes remain legible and the choice persists. |
| Inspect Actions and the page footer. | The deployed revision matches the successful workflow commit. |

## Design basis

The interaction uses an overview, a focused explanation and a connection to the next question. It is informed by [ScrollyVis (Mörth et al., 2023)](https://doi.org/10.1109/TVCG.2022.3205769). Direct navigation, complete reading pages and reduced-motion layouts address the usability concerns examined by [Mittenentzwei et al. (2023)](https://doi.org/10.1016/j.cag.2023.06.011). Repeatable build and test checks follow the continuous-integration approach reviewed by [Soares et al. (2022)](https://doi.org/10.1007/s10664-021-10114-1).

[USAvionix](https://www.usavionix.com/) informed scroll-driven changes in context and scale, [Lando Norris](https://landonorris.com/) the central opening composition, and [bleibtgleich](https://bleibtgleich.dev/) the navigation panels. The implementation uses project content and attributed media.

## Credits

The adapted opening film is **JudoVideo.net: Okuri-ashi-barai** by canaljudovideo, under CC BY 3.0. Full source, changes and license are in [media credits](public/media/CREDITS.md) and the website's Sources & credits panel. Roboto is supplied with its [SIL Open Font License](public/fonts/OFL.txt).

Scientific figures retain their source attribution. Embedded book figures retain the rights of their respective owners; they are not covered by a blanket project-artwork license.
