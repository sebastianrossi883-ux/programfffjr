#!/usr/bin/env python3
"""Select verified Guest, Framer and motion sources without immediate repeats."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path


ROOT = Path("/Users/utente/Downloads/reference_splitter")
COMPONENTS_ROOT = Path(
    "/Users/utente/Desktop/arsenal_v7/cartella senza nome 6final/componenti"
)
ANIMATIONS_ROOT = Path(
    "/Users/utente/Desktop/arsenal_v7/cartella senza nome 6final/ANIMAZIONI"
)
AMMO_ROOT = Path(
    "/Users/utente/Downloads/stitch_downloads/_ONE_SITE_JOBS/"
    "227b1915-f932-4744-bd06-e691c2285669-e23558e915/STITCH_AMMO_BOX"
)
FRAMER_SOURCE_BUNDLE = AMMO_ROOT / "REACT_FRAMER_INTERACTIVE_STITCH_BUNDLE.md"
LEDGER_PATH = ROOT / "MOTION_COMPONENT_LEDGER.json"
SELECTION_PATH = ROOT / "CURRENT_MOTION_SELECTION.json"
GENERATED_DIR = ROOT / "generated_motion"
GENERATED_COMPONENT_PATH = GENERATED_DIR / "SELECTED_COMPONENT_FOR_STITCH.md"
GENERATED_COMPONENT_2_PATH = GENERATED_DIR / "SELECTED_COMPONENT_2_FOR_STITCH.md"
GENERATED_FRAMER_PATH = GENERATED_DIR / "SELECTED_FRAMER_FOR_STITCH.md"
# Manifest immagini Guest: mappa ogni variabile CSS --gNimg-K al file originale
# a piena risoluzione, cosi' download_stitch_project.py (Stadio 2) puo'
# rimpiazzare i LQIP con le foto vere dopo il download. Vedi _inline_component_images.
GENERATED_IMAGE_MANIFEST_PATH = GENERATED_DIR / "GUEST_IMAGE_MANIFEST.json"
CATALOG_AUDIT_PATH = ROOT / "MOTION_CATALOG_AUDIT.json"
FRAMER_ARCHIVE_ROOT = ANIMATIONS_ROOT / "Framer_Interactions"
SUPPORT_LIBRARY_ROOTS = {
    "gsap-public": ANIMATIONS_ROOT / "gsap-public",
    "GSAP-master": ANIMATIONS_ROOT / "GSAP-master",
    "framer-motion": ANIMATIONS_ROOT / "framer-motion",
}
PORTABLE_SOURCE_SUFFIXES = {
    ".html", ".htm", ".css", ".scss", ".sass", ".js", ".mjs", ".cjs",
    ".ts", ".tsx", ".jsx", ".json", ".svg",
}
IGNORED_SOURCE_PARTS = {
    ".git", ".cache", "node_modules", "dist", "build", "coverage", "__MACOSX",
}


# Explicit canonical roots prevent accidental use of " 2", backup, __MACOSX,
# ZIP, WebGL or Three.js copies. Each entry was inspected for a complete DOM,
# style and executable interaction implementation.
CATALOG = (
    {
        "id": "codrops-scroll-carousel",
        "name": "Codrops CSS Scroll-Driven Carousel",
        "function": "mountCodropsScrollCarousel",
        "dom_value": "CodropsCarouselOriginal",
        "source_root": COMPONENTS_ROOT / "CodropsCarousels-main",
        "source_files": ("index.html", "css/shared.css", "css/demo1.css"),
        "required_tokens": ["animation-timeline", "scroll-timeline", "view-timeline"],
    },
    {
        "id": "reveal-slideshow",
        "name": "Codrops Reveal Slideshow",
        "function": "mountRevealSlideshow",
        "dom_value": "RevealSlideshowOriginal",
        "source_root": COMPONENTS_ROOT / "RevealSlideshow-master",
        "source_files": (
            "index.html", "css/base.css", "js/imagesloaded.pkgd.min.js",
            "js/TweenMax.min.js", "js/demo.js",
        ),
        "required_tokens": ["slide--current", "navigate", "TweenMax"],
    },
    {
        "id": "onscroll-filter",
        "name": "Codrops On-Scroll Filter",
        "function": "mountOnScrollFilter",
        "dom_value": "OnScrollFilterOriginal",
        "source_root": COMPONENTS_ROOT / "OnScrollFilter-main",
        "source_files": (
            "index.html", "css/base.css", "js/index.js", "js/item.js",
            "js/utils.js", "js/gsap.min.js", "js/Flip.min.js",
            "js/ScrollTrigger.min.js", "js/lenis.min.js",
        ),
        "required_tokens": ["Flip.getState", "Flip.from", "new Item"],
    },
    {
        "id": "hover-grid",
        "name": "Codrops Hover Grid",
        "function": "mountHoverGrid",
        "dom_value": "HoverGridOriginal",
        "source_root": COMPONENTS_ROOT / "HoverGrid-main",
        "source_files": (
            "index.html", "css/base.css", "js/index.js",
            "js/imagesloaded.pkgd.min.js", "js/utils.js", "js/gsap.min.js",
        ),
        "required_tokens": ["clipPathDirections", "tlEnter", "tlLeave"],
    },
    {
        "id": "one-element-scroll",
        "name": "Codrops One Element Scroll",
        "function": "mountOneElementScroll",
        "dom_value": "OneElementScrollOriginal",
        "source_root": COMPONENTS_ROOT / "OneElementScroll-main",
        "source_files": (
            "index.html", "css/base.css", "js/index.js", "js/Flip.min.js",
            "js/ScrollTrigger.min.js", "js/lenis.min.js", "js/gsap.min.js",
        ),
        "required_tokens": ["Flip.getState", "Flip.fit", "scrub: true"],
    },
    {
        "id": "scroll-shape-morph",
        "name": "Codrops On Scroll Shape Morph",
        "function": "mountScrollShapeMorph",
        "dom_value": "ScrollShapeMorphOriginal",
        "source_root": COMPONENTS_ROOT / "OnScrollShapeMorph-main",
        "source_files": (
            "index.html", "css/base.css", "js/index.js", "js/interactive-tilt.js",
            "js/ScrollTrigger.min.js", "js/lenis.min.js", "js/splitting.min.js",
            "js/gsap.min.js",
        ),
        "required_tokens": ["Splitting", "clipPaths", "ScrollTrigger"],
    },
    {
        "id": "grid-view-switch",
        "name": "Codrops Grid View Switch",
        "function": "mountGridViewSwitch",
        "dom_value": "GridViewSwitchOriginal",
        "source_root": COMPONENTS_ROOT / "GridViewSwitch-main",
        "source_files": (
            "index.html", "css/base.css", "js/index.js", "js/Flip.min.js",
            "js/imagesloaded.pkgd.min.js", "js/utils.js", "js/gsap.min.js",
        ),
        "required_tokens": ["Flip.getState", "Flip.from", "flipItem"],
    },
    {
        "id": "image-to-content",
        "name": "Codrops Image To Content",
        "function": "mountImageToContent",
        "dom_value": "ImageToContentOriginal",
        "source_root": COMPONENTS_ROOT / "ImageToContent-main",
        "source_files": (
            "src/index.html", "src/css/base.css", "src/js/index.js",
            "src/js/preview.js", "src/js/content.js", "src/js/utils.js",
            "src/js/textLinesReveal.js",
        ),
        "required_tokens": ["new Preview", "Flip", "animateOnScroll"],
    },
    {
        "id": "unreveal-effects",
        "name": "Codrops Unreveal Effects",
        "function": "mountUnrevealEffects",
        "dom_value": "UnrevealEffectsOriginal",
        "source_root": COMPONENTS_ROOT / "UnrevealEffects-main",
        "source_files": (
            "src/index.html", "src/css/base.css", "src/js/index.js",
            "src/js/contentItem.js", "src/js/previewItem.js", "src/js/utils.js",
        ),
        "required_tokens": ["new PreviewItem", "new ContentItem", "preview-open"],
    },
    {
        "id": "sticky-sections",
        "name": "Codrops Sticky Sections",
        "function": "mountStickySections",
        "dom_value": "StickySectionsOriginal",
        "source_root": COMPONENTS_ROOT / "StickySections-main",
        "source_files": (
            "index.html", "css/base.css", "js/demo1/index.js", "js/utils.js",
            "js/gsap.min.js", "js/ScrollTrigger.min.js", "js/lenis.min.js",
        ),
        "required_tokens": ["content--sticky", "ScrollTrigger", "new Lenis"],
    },
    {
        "id": "intro-trail",
        "name": "Codrops Intro Trail Effect",
        "function": "mountIntroTrail",
        "dom_value": "IntroTrailOriginal",
        "source_root": COMPONENTS_ROOT / "IntroTrailEffect-main",
        "source_files": (
            "src/index.html", "src/css/base.css", "src/js/index.js",
            "src/js/trail.js", "src/js/fakeProgress.js", "src/js/textLinesReveal.js",
            "src/js/gsapAnimation.js", "src/js/utils.js",
        ),
        "required_tokens": ["new TrailImage", "new TrailText", "Flip.from"],
    },
    {
        "id": "image-stack-grid",
        "name": "Codrops Image Stack Grid",
        "function": "mountImageStackGrid",
        "dom_value": "ImageStackGridOriginal",
        "source_root": COMPONENTS_ROOT / "ImageStackGrid-main",
        "source_files": (
            "src/index.html", "src/css/base.css", "src/css/demo1.css",
            "src/js/demo1/index.js", "src/js/demo1/galleryController.js",
            "src/js/demo1/galleryItem.js", "src/js/cursor.js", "src/js/utils.js",
        ),
        "required_tokens": ["new GalleryController", "GalleryItem", "Cursor"],
    },
    {
        "id": "draggable-grid",
        "name": "Codrops Draggable Grid",
        "function": "mountDraggableGrid",
        "dom_value": "DraggableGridOriginal",
        "source_root": COMPONENTS_ROOT / "draggable-grid-main",
        "source_files": (
            "index.html", "css/base.css", "css/style.css", "js/app.js",
            "js/gsap.js", "js/Draggable.js", "js/Flip.js", "js/SplitText.js",
            "js/utils.js", "js/imagesloaded.pkgd.min.js",
        ),
        "required_tokens": ["class Grid", "Draggable", "--is-dragging"],
    },
    {
        "id": "page-flip-layout",
        "name": "Codrops Page Flip Layout",
        "function": "mountPageFlipLayout",
        "dom_value": "PageFlipLayoutOriginal",
        "source_root": COMPONENTS_ROOT / "PageFlipLayout-master",
        "source_files": (
            "index.html", "css/base.css", "js/demo.js",
            "js/TweenMax.min.js", "js/imagesloaded.pkgd.min.js",
        ),
        "required_tokens": ["class PageTurn", "new TimelineMax", "revealer__item-inner"],
    },
    {
        "id": "diagonal-thumbnails",
        "name": "Codrops Diagonal Thumbnails",
        "function": "mountDiagonalThumbnails",
        "dom_value": "DiagonalThumbnailsOriginal",
        "source_root": COMPONENTS_ROOT / "DiagonalThumbnails-master",
        "source_files": (
            "src/index.html", "src/css/base.css", "src/js/demo1/index.js",
            "src/js/demo1/slideshow.js", "src/js/slide.js", "src/js/cursor.js",
            "src/js/utils.js",
        ),
        "required_tokens": ["new Slideshow", "Slide", "Cursor"],
    },
    {
        "id": "scroll-panels",
        "name": "Codrops Scroll Panels",
        "function": "mountScrollPanels",
        "dom_value": "ScrollPanelsOriginal",
        "source_root": COMPONENTS_ROOT / "ScrollPanels-main",
        "source_files": (
            "src/index.html", "src/css/base.css", "src/js/index.js", "src/js/utils.js",
        ),
        "required_tokens": ["gsap.registerPlugin", "ScrollTrigger", "new Lenis"],
    },
    {
        "id": "crossroads-slideshow",
        "name": "Codrops Crossroads Slideshow",
        "function": "mountCrossroadsSlideshow",
        "dom_value": "CrossroadsSlideshowOriginal",
        "source_root": COMPONENTS_ROOT / "CrossroadsSlideshow-master/CrossroadsSlideshow-master",
        "source_files": (
            "index.html", "css/base.css", "js/demo.js", "js/TweenMax.min.js",
            "js/charming.min.js", "js/imagesloaded.pkgd.min.js",
        ),
        "required_tokens": ["class Slide", "new TimelineMax", "grid__item--center"],
    },
    {
        "id": "sticky-grid-scroll",
        "name": "Codrops Sticky Grid Scroll",
        "function": "mountStickyGridScroll",
        "dom_value": "StickyGridScrollOriginal",
        "source_root": COMPONENTS_ROOT / "codrops-sticky-grid-scroll-main",
        "source_files": (
            "src/index.html", "src/styles/base.css", "src/styles/index.css",
            "src/scripts/index.js", "src/scripts/utils.js",
        ),
        "required_tokens": ["class StickyGridScroll", "ScrollTrigger", "gsap.timeline"],
    },
    {
        "id": "flip-toggle-view",
        "name": "GSAP Flip Toggle View",
        "function": "mountFlipToggleView",
        "dom_value": "FlipToggleViewOriginal",
        "source_root": COMPONENTS_ROOT / "GSAP Flip - Toggle View",
        "source_files": ("index.html", "styles.css", "script.js"),
        "required_tokens": ["Flip.getState", "Flip.from", "applyRotation"],
    },
    {
        "id": "scroll-transition",
        "name": "GSAP Scroll Transition",
        "function": "mountScrollTransition",
        "dom_value": "ScrollTransitionOriginal",
        "source_root": COMPONENTS_ROOT / "Scroll-Transition-main",
        "source_files": (
            "index.html", "css/style.css", "js/script.js", "js/gsap.min.js",
            "js/ScrollTrigger.min.js", "js/lenis.min.js",
        ),
        "required_tokens": ["createBlinds", "ScrollTrigger", "new Lenis"],
    },
    {
        "id": "exhibition-rooms",
        "name": "Codrops Exhibition Rooms",
        "function": "mountExhibitionRooms",
        "dom_value": "ExhibitionRoomsOriginal",
        "source_root": COMPONENTS_ROOT / "Exhibition-master",
        "source_files": (
            "index.html", "css/normalize.css", "css/demo.css",
            "js/anime.min.js", "js/imagesloaded.pkgd.min.js", "js/main.js",
        ),
        "required_tokens": ["DOM.scroller", "DOM.rooms", "requestAnimationFrame"],
    },
    {
        "id": "segment-effect",
        "name": "Codrops Segment Effect",
        "function": "mountSegmentEffect",
        "dom_value": "SegmentEffectOriginal",
        "source_root": COMPONENTS_ROOT / "SegmentEffect-master",
        "source_files": (
            "index.html", "css/normalize.css", "css/demo.css",
            "css/component.css", "js/anime.min.js",
            "js/imagesloaded.pkgd.min.js", "js/main.js",
        ),
        "required_tokens": ["function Segmenter", "anime(animProps)", "mousemove"],
    },
    {
        "id": "kinetic-gradient-slider",
        "name": "Kinetic Gradient Slider",
        "function": "mountKineticGradientSlider",
        "dom_value": "KineticGradientSliderOriginal",
        "source_root": COMPONENTS_ROOT / "gradientslider-main",
        "source_files": ("index.html", "base.css", "styles.css", "script.js"),
        "required_tokens": ["updateCarouselTransforms", "requestAnimationFrame", "pointermove"],
    },
    {
        "id": "codrops-parallax-slider",
        "name": "Codrops Parallax Slider",
        "function": "mountCodropsParallaxSlider",
        "dom_value": "CodropsParallaxSliderOriginal",
        "source_root": COMPONENTS_ROOT / "codrops-parallax-slider-master",
        "source_files": (
            "package.json", "src/index.html", "src/index.js", "src/index.scss",
            "src/store/index.js", "src/utils/math.js", "src/utils/scroll.js",
            "src/components/placeholders/placeholders.js",
            "src/components/placeholders/placeholders.scss",
            "src/components/slider/slider.js", "src/components/slider/slider.scss",
            "src/components/button-slider-open/button-slider-open.scss",
            "src/styles/aspect-ratio.scss", "src/styles/base.scss",
            "src/styles/button.scss", "src/styles/container.scss",
            "src/styles/fonts.scss", "src/styles/reset.scss",
            "src/styles/type.scss", "src/styles/vars.scss",
        ),
        "required_tokens": ["new Scroll", "new Slider", "new Placeholders"],
    },
    {
        "id": "telescope-zoom",
        "name": "GSAP Telescope Zoom",
        "function": "mountTelescopeZoom",
        "dom_value": "TelescopeZoomOriginal",
        "source_root": COMPONENTS_ROOT / "telescope-zoom-main",
        "source_files": (
            "package.json", "index.html", "src/base.css", "src/style.css",
            "src/utils.js", "src/main.js",
        ),
        "required_tokens": ["ScrollSmoother.create", "gsap.timeline", "scrub: true"],
    },
    {
        "id": "premium-flip-gallery",
        "name": "GSAP Premium Flip Gallery",
        "function": "GuestFlipGallery",
        "dom_value": "PremiumFlipGalleryOriginal",
        "source_root": COMPONENTS_ROOT / "GOLDEN_ARTISANAL_016_PREMIUM_FLIP",
        "source_files": ("GuestFlipGallery.tsx", "GuestFlipGallery.module.css"),
        "required_tokens": ["Flip.getState", "Flip.fit", "useGSAP"],
    },
    {
        "id": "kettmeir-cinematic-hero",
        "name": "Kettmeir Cinematic Hero",
        "function": "KettmeirCinematicHero",
        "dom_value": "KettmeirCinematicHeroOriginal",
        "source_root": COMPONENTS_ROOT / "GOLDEN_ARTISANAL_017_KETTMEIR_HERO",
        "source_files": (
            "package.json", "src/App.tsx", "src/App.css", "src/index.css",
            "src/main.tsx",
        ),
        "required_tokens": ["useGSAP", "ScrollTrigger", "clipPath"],
    },
    {
        "id": "morphing-page-transition",
        "name": "Codrops Morphing Page Transition",
        "function": "mountMorphingPageTransition",
        "dom_value": "MorphingPageTransitionOriginal",
        "source_root": COMPONENTS_ROOT / "MorphingPageTransition-master",
        "source_files": (
            "index.html", "css/normalize.css", "css/demo.css",
            "js/anime.min.js", "js/charming.min.js",
            "js/imagesloaded.pkgd.min.js", "js/demo1.js",
        ),
        "required_tokens": ["const navigate", "anime({", "DOM.enter"],
    },
    {
        "id": "outdoors-transition",
        "name": "Codrops Outdoors Transition",
        "function": "mountOutdoorsTransition",
        "dom_value": "OutdoorsTransitionOriginal",
        "source_root": COMPONENTS_ROOT / "OutdoorsTemplate-master",
        "source_files": (
            "index.html", "css/base.css", "js/main.js", "js/anime.min.js",
            "js/charming.min.js", "js/imagesloaded.pkgd.min.js",
        ),
        "required_tokens": ["class Entry", "class Slideshow", "new Slideshow"],
    },
    {
        "id": "theodore-menu-transition",
        "name": "Codrops Theodore Infinite Menu",
        "function": "mountTheodoreMenuTransition",
        "dom_value": "TheodoreMenuTransitionOriginal",
        "source_root": COMPONENTS_ROOT / "Theodore-main",
        "source_files": (
            "src/index.html", "src/css/base.css", "src/js/index.js",
            "src/js/utils.js",
        ),
        "required_tokens": ["gsap.timeline", "openMenu", "closeMenu"],
    },
    {
        "id": "perspective-scroll-gallery",
        "name": "GSAP Perspective Scroll Gallery",
        "function": "mountPerspectiveScrollGallery",
        "dom_value": "PerspectiveScrollGalleryOriginal",
        "source_root": COMPONENTS_ROOT / "gsap-scrolltrigger-main",
        "source_files": (
            "index.html", "src/main.ts", "src/style.css",
            "src/parallax-sections.css", "src/perspective-gallery.scss",
        ),
        "required_tokens": ["setupPerspectiveGallery", "setupParallaxSections", "scrub: true"],
    },
)


# ---------------------------------------------------------------------------
# CARTELLA UNIVERSALE
#
# Le voci qui sopra sono scritte a mano, una per una. Da qui in poi non serve
# piu': si mette un componente (cartella o .zip) dentro CARTELLA_UNIVERSALE,
# si lancia `python3 componenti_universali.py`, e la voce nasce da sola con la
# stessa forma - id, funzione mount, valore root, file sorgente e i token
# letterali pescati dal codice vero.
#
# Le voci automatiche si aggiungono, non sostituiscono: un id gia' presente nel
# catalogo scritto a mano vince, cosi' aggiungere una cartella non puo'
# cambiare in silenzio un componente gia' collaudato.
# ---------------------------------------------------------------------------
CARTELLA_UNIVERSALE = Path(__file__).resolve().parent / "componenti"
CATALOGO_UNIVERSALE_JSON = Path(__file__).resolve().parent / "CATALOGO_COMPONENTI.json"


def _dentro(percorso: Path, radice: Path) -> bool:
    try:
        percorso.relative_to(radice)
    except ValueError:
        return False
    return True


def _catalogo_dalla_cartella() -> tuple[dict, ...]:
    if not CATALOGO_UNIVERSALE_JSON.is_file():
        return ()
    try:
        dati = json.loads(CATALOGO_UNIVERSALE_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Catalogo automatico illeggibile, uso solo quello scritto a mano: {exc}")
        return ()

    gia_presenti = {voce["id"] for voce in CATALOG}
    voci: list[dict] = []
    for voce in dati.get("componenti", []):
        if voce["id"] in gia_presenti:
            continue
        radice = Path(voce["source_root"])
        if not radice.is_dir():
            continue
        voci.append(
            {
                "id": voce["id"],
                "name": voce.get("name") or voce["id"],
                "function": voce["function"],
                "dom_value": voce["dom_value"],
                "source_root": radice,
                "source_files": tuple(voce["source_files"]),
                "required_tokens": list(voce["required_tokens"]),
            }
        )
    if voci:
        print(f"Catalogo automatico: {len(voci)} componenti da {CARTELLA_UNIVERSALE}")
    return tuple(voci)


CATALOG = CATALOG + _catalogo_dalla_cartella()


FRAMER_CATALOG = (
    {
        "id": "framer-stryds",
        "name": "Framer Stryds Interactive",
        "filename": "StrydsInteractiveReact.tsx",
        "function": "StrydsInteractiveReact",
        "dom_value": "StrydsInteractiveOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/stryds.learnframer.site",
        "required_tokens": ["useGSAP", "ScrollTrigger", "clipPath", "scrub: 1"],
    },
    {
        "id": "framer-scroll-mask",
        "name": "Framer Scroll Mask",
        "filename": "ScrollMaskInteractiveReact.tsx",
        "function": "ScrollMaskInteractiveReact",
        "dom_value": "ScrollMaskInteractiveOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/scroll-mask.learnframer.site",
        "required_tokens": ["useGSAP", "ScrollTrigger", "clipPath", "scrub: true"],
    },
    {
        "id": "framer-wiper",
        "name": "Framer Wiper Transition",
        "filename": "WiperTransitionReact.tsx",
        "function": "WiperTransitionReact",
        "dom_value": "WiperTransitionOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/wiper.framer.website",
        "required_tokens": ["useGSAP", "ScrollTrigger", "clipPath", "power3.inOut"],
    },
    {
        "id": "framer-4k-video",
        "name": "Framer 4K Video Scroll",
        "source_mode": "native_archive",
        "function": "mountFramer4KVideoOriginal",
        "dom_value": "Framer4KVideoOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/4kvideo.framer.website",
        "source_file": "website-d6a3ebe3-64eb-4a2a-8c91-eecc1b2bd2db/index.html",
        "module_url": "https://framerusercontent.com/sites/5vXyFo5SCquGZ4idckJE0B/default_script0.UA2RN5KI.mjs",
        "required_tokens": ["data-framer-name", "data-framer-component-type", "default_script0.UA2RN5KI.mjs"],
    },
    {
        "id": "framer-circle-hover",
        "name": "Framer Circle Hover",
        "source_mode": "native_archive",
        "function": "mountFramerCircleHoverOriginal",
        "dom_value": "FramerCircleHoverOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/circle-hover.learnframer.site",
        "source_file": "website-fb73dc0e-e158-4777-974a-5adb6a41ce5f/index.html",
        "module_url": "https://framerusercontent.com/sites/1ajJpNqYPlVos6ve1RVZoc/script_main.C9YFHAMd.mjs",
        "required_tokens": ["data-framer-name", "data-framer-component-type", "script_main.C9YFHAMd.mjs"],
    },
    {
        "id": "framer-curved-scroll",
        "name": "Framer Curved Scroll",
        "source_mode": "native_archive",
        "function": "mountFramerCurvedScrollOriginal",
        "dom_value": "FramerCurvedScrollOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/curvedscroll.framer.website",
        "source_file": "website-2b78f874-5553-40cb-ba31-23cd2cff69eb/index.html",
        "module_url": "https://framerusercontent.com/sites/oBGryba9n9lG81WCscf8Y/_script0.BCU3XFUA.mjs",
        "required_tokens": ["data-framer-name", "data-framer-component-type", "_script0.BCU3XFUA.mjs"],
    },
    {
        "id": "framer-image-intro",
        "name": "Framer Image Intro",
        "source_mode": "native_archive",
        "function": "mountFramerImageIntroOriginal",
        "dom_value": "FramerImageIntroOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/image-intro.learnframer.site",
        "source_file": "website-0ccaa0e9-05e0-480d-b080-0abb07fe8ae2/index.html",
        "module_url": "https://framerusercontent.com/sites/5vdKJHZztQkJ1E6Gv68kHu/script_main.PJD6DYTR.mjs",
        "required_tokens": ["data-framer-name", "data-framer-component-type", "script_main.PJD6DYTR.mjs"],
    },
    {
        "id": "framer-immerse-zoom",
        "name": "Framer Immerse Zoom",
        "source_mode": "native_archive",
        "function": "mountFramerImmerseZoomOriginal",
        "dom_value": "FramerImmerseZoomOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/immerse-zoom.learnframer.site",
        "source_file": "website-a6006e3b-41a1-4951-8ae2-4a70fbf7c447/index.html",
        "module_url": "https://framerusercontent.com/sites/3GuS0yfNCKnhEbR0CsII8W/script_main.AKL4ZBMX.mjs",
        "required_tokens": ["data-framer-name", "data-framer-component-type", "script_main.AKL4ZBMX.mjs"],
    },
    {
        "id": "framer-on-scroll",
        "name": "Framer On Scroll",
        "source_mode": "native_archive",
        "function": "mountFramerOnScrollOriginal",
        "dom_value": "FramerOnScrollOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/onscroll.framer.website",
        "source_file": "website-ee976828-09bd-43f5-a55e-b62a9b99d40f/index.html",
        "module_url": "https://framerusercontent.com/sites/5D83pM5ZWH3pZiYeNL1cS8/_script0.DTNOUNJP.mjs",
        "required_tokens": ["data-framer-name", "data-framer-component-type", "_script0.DTNOUNJP.mjs"],
    },
    {
        "id": "framer-rotating-zoom-entrance",
        "name": "Framer Rotating Zoom Entrance",
        "source_mode": "native_archive",
        "function": "mountFramerRotatingZoomEntranceOriginal",
        "dom_value": "FramerRotatingZoomEntranceOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/rotatingzoomenterance.framer.website",
        "source_file": "website-a21051d0-3eaa-47ea-a8f4-eec41ab48ea0/index.html",
        "module_url": "https://framerusercontent.com/sites/4N0Y93Jselmokk1c6bzvIT/default_script0.ZOFEKQZP.mjs",
        "required_tokens": ["data-framer-name", "data-framer-component-type", "default_script0.ZOFEKQZP.mjs"],
    },
    {
        "id": "framer-sign-animation",
        "name": "Framer Sign Animation",
        "source_mode": "native_archive",
        "function": "mountFramerSignAnimationOriginal",
        "dom_value": "FramerSignAnimationOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/sign-anim.learnframer.site",
        "source_file": "website-b001b1ab-0d35-4376-b702-f01f566c15cb/index.html",
        "module_url": "https://framerusercontent.com/sites/2PruFmGR0490fhyI2Vchx6/script_main.RQ1cnwon.mjs",
        "required_tokens": ["data-framer-name", "data-framer-component-type", "script_main.RQ1cnwon.mjs"],
    },
    {
        "id": "framer-university",
        "name": "Framer University Interaction",
        "source_mode": "native_archive",
        "function": "mountFramerUniversityOriginal",
        "dom_value": "FramerUniversityOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/university.learnframer.site",
        "source_file": "website-7f53a862-e489-4d31-85b7-a7324813ea03/index.html",
        "module_url": "https://framerusercontent.com/sites/5M98tg7cUFQpT6qyQB2dsz/default_script0.PXSVPCEP.mjs",
        "required_tokens": ["data-framer-name", "data-framer-component-type", "default_script0.PXSVPCEP.mjs"],
    },
    {
        "id": "framer-vaporize",
        "name": "Framer Vaporize",
        "source_mode": "native_archive",
        "function": "mountFramerVaporizeOriginal",
        "dom_value": "FramerVaporizeOriginal",
        "origin": ANIMATIONS_ROOT / "Framer_Interactions/vaporize.learnframer.site",
        "source_file": "website-5683b9ed-7402-49f3-846d-e54f0c0adbbc/index.html",
        "module_url": "https://framerusercontent.com/sites/1Bu7CbutvRnbqn7eVA9wnD/script_main.5WDGMLVT.mjs",
        "required_tokens": ["data-framer-name", "data-framer-component-type", "script_main.5WDGMLVT.mjs"],
    },
)


MOTION_STYLE_PROFILES = (
    {"id": "editorial-veil", "name": "Editorial Veil", "direction": "mask reveal, optical scale, linee e micro-parallax"},
    {"id": "cinematic-depth", "name": "Cinematic Depth", "direction": "depth scale, parole in controtempo, parallax 10-14%"},
    {"id": "horizontal-narrative", "name": "Horizontal Narrative", "direction": "scrub orizzontale, counter-scroll e progress sincronizzato"},
    {"id": "split-architecture", "name": "Split Architecture", "direction": "masse opposte, clip laterali e coppie testo-media"},
    {"id": "quiet-luxury", "name": "Quiet Luxury", "direction": "line reveal lento, optical scale e micro-risposte precise"},
    {"id": "gallery-drift", "name": "Gallery Drift", "direction": "drift differenziato, didascalie ancorate e focus di profondita"},
)


COMPONENT_DUPLICATES = {
    "GridViewSwitch": "GridViewSwitch-main",
    "GridViewSwitch_Michelin": "GridViewSwitch-main",
    "OnScrollFilterReact": "OnScrollFilter-main",
    "RevealSlideshow": "RevealSlideshow-master",
    "RevealSlideshowReact": "RevealSlideshow-master",
    "SegmentEffectReact": "SegmentEffect-master",
    "TelescopeZoomReact": "telescope-zoom-main",
    "UnrevealEffects": "UnrevealEffects-main",
    "GOLDEN_ARTISANAL_007_PARALLAX_SLIDER": "codrops-parallax-slider-master",
    "GOLDEN_ARTISANAL_008_STICKY_GRID": "codrops-sticky-grid-scroll-main",
    "GOLDEN_ARTISANAL_009_EXHIBITION": "Exhibition-master",
    "GOLDEN_ARTISANAL_010_HOVER_GRID": "HoverGrid-main",
    "GOLDEN_ARTISANAL_012_INTRO_TRAIL": "IntroTrailEffect-main",
    "GOLDEN_ARTISANAL_014_MORPHING_PAGE_TRANSITION": "MorphingPageTransition-master",
    "GOLDEN_ARTISANAL_015_ONE_ELEMENT_SCROLL": "OneElementScroll-main",
    "GOLDEN_ARTISANAL_016_ON_SCROLL_FILTER": "OnScrollFilter-main",
}

COMPONENT_COLLECTIONS = {
    "cartella senza nome": "aggregate archive containing several source projects",
    "cartella senza nome 3": "aggregate archive containing several source projects",
    "codrops-react-library": "React conversion collection, not one autonomous component",
    "golden-vault": "Golden component collection, not one autonomous component",
    "GSAP-master": "support library, not a Guest Component",
    "delphi-main": "complete AI Studio application, not a portable Guest Component",
}

COMPONENT_DEDICATED_PIPELINE = {
    "flat-surface-shader-master": "shader engine",
    "gooey-hover-codrops-master": "WebGL/GLSL effect",
    "GOLDEN_ARTISANAL_006_HORIZONTAL_PARALLAX": "Three.js/WebGL variant",
    "GOLDEN_ARTISANAL_006_HORIZONTAL_PARALLAX_REACT_FINAL": "Three.js/WebGL React variant",
    "GOLDEN_ARTISANAL_011_INFINITE_CANVAS": "canvas engine",
    "GOLDEN_ARTISANAL_013_MORPHING_2D": "Canvas2D engine",
    "GOLDEN_ARTISANAL_013_MORPHING_2D_BACKUP": "backup of Canvas2D engine",
    "GsapThreejs_Michelin_Wipe": "Three.js/GLSL effect",
    "gsap-threejs-codrops-master": "Three.js/GLSL effect",
    "horizontal-parallax-gallery-codrops-master": "source imports Three.js and shader code",
    "infinite-canvas-main": "canvas engine",
    "morphing-2d-demo-main": "Canvas2D engine",
    "Shader-Image-Transition-main": "shader engine",
    "UnrollingImages-master": "WebGL/GLSL effect",
    "webGLImageTransitions-master": "WebGL effect",
    "webGLImageTransitionsReact": "WebGL React conversion",
}


def _component_archive_inventory() -> list[dict]:
    """Account for every top-level source directory without inflating the rotation."""
    selected_roots = {
        Path(entry["source_root"]).relative_to(COMPONENTS_ROOT).parts[0]: entry["id"]
        for entry in CATALOG
    }
    rows: list[dict] = []
    for path in sorted(COMPONENTS_ROOT.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_dir() or path.name == "__MACOSX":
            continue
        files = [
            item for item in path.rglob("*")
            if item.is_file() and "__MACOSX" not in item.parts and item.name != ".DS_Store"
        ]
        name = path.name
        if not files:
            status, reason = "empty_copy_ignored", "empty directory"
        elif re.search(r"\s+[234]$", name):
            status, reason = "suffix_copy_ignored", "duplicate directory with numeric suffix"
        elif name.startswith("temp_"):
            status, reason = "temporary_ignored", "temporary working directory"
        elif name in selected_roots:
            status = "portable_original_verified"
            reason = f"rotation id: {selected_roots[name]}"
        elif name in COMPONENT_DUPLICATES:
            status = "duplicate_or_conversion_ignored"
            reason = f"canonical source: {COMPONENT_DUPLICATES[name]}"
        elif name in COMPONENT_COLLECTIONS:
            status = "collection_or_library_not_rotated"
            reason = COMPONENT_COLLECTIONS[name]
        elif name in COMPONENT_DEDICATED_PIPELINE:
            status = "requires_webgl_canvas_pipeline"
            reason = COMPONENT_DEDICATED_PIPELINE[name]
        else:
            status, reason = "requires_manual_classification", "not yet admitted to the verified rotation"
        rows.append({
            "id": name,
            "root": str(path),
            "file_count": len(files),
            "status": status,
            "reason": reason,
        })
    return rows


def validate_catalog() -> dict:
    """Fail closed when a catalog entry is duplicated, copied or incomplete."""
    forbidden_path = re.compile(
        r"(?:^|/)(?:__MACOSX|temp[^/]*|backup[^/]*)(?:/|$)|"
        r"(?:^|/)[^/]+\s+2(?:/|$)|\.(?:zip|tar|tgz)$|"
        r"(?:webgl|threejs|shader|infinite-canvas)",
        re.I,
    )
    ids: set[str] = set()
    component_rows: list[dict] = []
    for entry in CATALOG:
        component_id = entry["id"]
        if component_id in ids:
            raise RuntimeError(f"ID componente duplicato: {component_id}")
        ids.add(component_id)
        root = Path(entry["source_root"])
        if forbidden_path.search(str(root)):
            raise RuntimeError(f"Componente non canonico o non portabile: {root}")
        # Due fonti autorevoli: l'arsenale storico e la cartella universale.
        # Fuori da queste due non si pesca niente, altrimenti basterebbe un
        # percorso sbagliato nel JSON per far integrare a Stitch un file a caso.
        radici_ammesse = (COMPONENTS_ROOT, CARTELLA_UNIVERSALE)
        if not any(_dentro(root, ammessa) for ammessa in radici_ammesse):
            raise RuntimeError(
                f"Componente fuori dalle fonti autorevoli {radici_ammesse}: {root}"
            )
        sources = _source_paths(entry)
        missing = [str(path) for path in sources if not path.is_file()]
        if missing:
            raise RuntimeError(f"Sorgenti mancanti per {component_id}: {missing}")
        source_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore") for path in sources
        )
        missing_tokens = [token for token in entry["required_tokens"] if token not in source_text]
        if missing_tokens:
            raise RuntimeError(f"Token originali mancanti per {component_id}: {missing_tokens}")
        component_rows.append({
            "id": component_id,
            "root": str(root),
            "files": len(sources),
            "status": "portable_original_verified",
        })

    framer_ids: set[str] = set()
    framer_rows: list[dict] = []
    for entry in FRAMER_CATALOG:
        framer_id = entry["id"]
        if framer_id in framer_ids:
            raise RuntimeError(f"ID Framer duplicato: {framer_id}")
        framer_ids.add(framer_id)
        origin = Path(entry["origin"])
        try:
            origin.relative_to(ANIMATIONS_ROOT / "Framer_Interactions")
        except ValueError as exc:
            raise RuntimeError(f"Framer fuori dalla fonte autorevole: {origin}") from exc
        code, source_hash = _extract_framer(entry)
        missing_tokens = [token for token in entry["required_tokens"] if token not in code]
        if missing_tokens:
            raise RuntimeError(f"Token Framer mancanti per {framer_id}: {missing_tokens}")
        source_mode = entry.get("source_mode", "portable_react")
        framer_rows.append({
            "id": framer_id,
            "origin": str(origin),
            "sha256": source_hash,
            "status": (
                "native_archive_verified"
                if source_mode == "native_archive"
                else "portable_react_verified"
            ),
        })

    portable_framer_origins = {Path(entry["origin"]).name for entry in FRAMER_CATALOG}
    archived_framer: list[dict] = []
    if FRAMER_ARCHIVE_ROOT.is_dir():
        for path in sorted(FRAMER_ARCHIVE_ROOT.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_dir() or path.name in {"__MACOSX", "Framer_Interactions"}:
                continue
            html_files = sorted(path.rglob("*.html"))
            archived_framer.append({
                "id": path.name,
                "root": str(path),
                "html_files": len(html_files),
                "status": (
                    "verified_rotation_source"
                    if path.name in portable_framer_origins
                    else "archive_only_not_portable"
                ),
                "reason": (
                    "admitted as exact React or native Framer runtime source"
                    if path.name in portable_framer_origins
                    else "Framer export requires its remote hydration/runtime; no autonomous module found"
                ),
            })

    support_libraries = []
    for library_id, path in SUPPORT_LIBRARY_ROOTS.items():
        if not path.is_dir():
            raise RuntimeError(f"Libreria di supporto mancante: {path}")
        support_libraries.append({
            "id": library_id,
            "root": str(path),
            "status": "support_library_not_rotated_as_component",
        })

    component_archive = _component_archive_inventory()
    report = {
        "components_root": str(COMPONENTS_ROOT),
        "animations_root": str(ANIMATIONS_ROOT),
        "component_count": len(component_rows),
        "framer_count": len(framer_rows),
        "component_source_directory_count": len(component_archive),
        "framer_source_directory_count": len(archived_framer),
        "components": component_rows,
        "component_archive_inventory": component_archive,
        "framer_interactions": framer_rows,
        "framer_archive_inventory": archived_framer,
        "support_libraries": support_libraries,
        "excluded_classes": [
            "zip", "__MACOSX", "temporary", "suffix-copy-2", "backup",
            "WebGL", "Three.js", "shader", "canvas-engine",
        ],
    }
    CATALOG_AUDIT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def _read_json(path: Path, default: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _batch_fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name.lower()):
        stat = path.stat()
        digest.update(path.name.encode("utf-8", "ignore"))
        digest.update(str(stat.st_size).encode("ascii"))
        with path.open("rb") as handle:
            digest.update(handle.read(65536))
    return digest.hexdigest()


def _source_paths(entry: dict) -> list[Path]:
    """Solo i file dichiarati in `source_files`: niente rastrellamento cartella.

    Prima qui si faceva `explicit + discovered`, con un `rglob("*")` su tutta la
    cartella del componente. Risultato: nel bundle finivano `package-lock.json`
    (32 KB di lockfile npm!), `tsconfig.json`, `vite.config.js` e sorgenti
    `.ts/.scss` non eseguibili in un export HTML statico. Stitch si trovava a
    dover incollare - e a dichiarare lo SHA256 di - roba che non c'entra nulla
    col componente, e cedeva.

    `source_files` e' curato a mano per ogni voce del CATALOG: e' la lista dei
    file che servono davvero. Verificato su tutti e 31 i componenti: usando solo
    i dichiarati, NESSUNO perde i propri `required_tokens`.
    """
    root = Path(entry["source_root"])
    declared = [root / relative for relative in entry["source_files"]]
    return sorted(
        {path for path in declared if path.is_file()},
        key=lambda path: str(path.relative_to(root)).lower(),
    )


# File che NON vanno mai spediti a Stitch: sono gia' caricati via CDN nella
# pagina, oppure sono demo duplicate/asset che gonfiano il bundle. Un bundle da
# 150-200 KB non viene incollato: Stitch si arrende e scrive un placeholder
# (mentre il bundle Framer da 1 KB viene iniettato 1:1). Tenere il Guest piccolo
# e' l'unica cosa che lo rende davvero iniettabile.
_VENDOR_ALREADY_ON_CDN = (
    "gsap.min.js", "gsap.js", "scrolltrigger.min.js", "scrolltrigger.js",
    "flip.min.js", "flip.js", "draggable.min.js", "draggable.js",
    "tweenmax.min.js", "tweenmax.js", "lenis.min.js", "lenis.js",
    "imagesloaded.pkgd.min.js", "imagesloaded.min.js",
    "splitting.min.js", "normalize.css", "three.min.js", "three.js",
)
_DUPLICATE_ENTRY_NAMES = ("index2.", "index3.", "index4.", "index5.", "demo2.", "demo3.")

# Configurazione di build: non e' codice del componente e in un export HTML
# statico non serve a niente. Alcune voci del CATALOG se la portano dietro
# dentro `source_files`, quindi va filtrata anche li'.
_BUILD_CONFIG_FILES = (
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "tsconfig.json", "tsconfig.node.json", "vite.config.js", "vite.config.ts",
    "webpack.config.js", "rollup.config.js", ".eslintrc.json", "postcss.config.js",
)


def _is_injectable_source(source: Path) -> bool:
    """Tiene solo cio' che serve davvero a far girare il componente."""
    name = source.name.lower()
    if name in _VENDOR_ALREADY_ON_CDN:
        return False
    if name in _BUILD_CONFIG_FILES:
        return False
    if any(name.startswith(dup) for dup in _DUPLICATE_ENTRY_NAMES):
        return False
    if source.suffix.lower() in {".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return False
    return True


def _package_sources(entry: dict) -> tuple[str, dict[str, str]]:
    blocks: list[str] = []
    hashes: dict[str, str] = {}
    root = Path(entry["source_root"])
    selected = [s for s in _source_paths(entry) if _is_injectable_source(s)]
    if not selected:
        selected = _source_paths(entry)
    for source in selected:
        if not source.is_file():
            raise RuntimeError(f"Sorgente originale non trovato: {source}")
        raw = source.read_bytes()
        relative = str(source.relative_to(root))
        digest = hashlib.sha256(raw).hexdigest()
        hashes[relative] = digest
        language = {
            ".html": "html", ".htm": "html", ".css": "css", ".scss": "scss",
            ".sass": "sass", ".js": "javascript", ".mjs": "javascript",
            ".cjs": "javascript", ".ts": "typescript", ".tsx": "tsx",
            ".jsx": "jsx", ".json": "json", ".svg": "xml",
        }.get(source.suffix.lower(), "text")
        blocks.append(
            f"## ORIGINAL FILE: `{relative}`\nSHA256: `{digest}`\n\n"
            f"```{language}\n{raw.decode('utf-8', 'ignore')}\n```"
        )
    return "\n\n".join(blocks), hashes


def _extract_framer(entry: dict) -> tuple[str, str]:
    origin = Path(entry["origin"])
    if not origin.is_dir():
        raise RuntimeError(f"Sorgente Framer verificato mancante: {entry['name']}")
    if entry.get("source_mode") == "native_archive":
        source = origin / entry["source_file"]
        if not source.is_file():
            raise RuntimeError(f"Archivio Framer originale mancante: {source}")
        code = source.read_text(encoding="utf-8", errors="strict")
        if entry["module_url"] not in code:
            raise RuntimeError(
                f"Modulo runtime Framer originale non trovato in {source}: {entry['module_url']}"
            )
        return code, hashlib.sha256(source.read_bytes()).hexdigest()
    if not FRAMER_SOURCE_BUNDLE.is_file():
        raise RuntimeError(f"Bundle React Framer verificato mancante: {FRAMER_SOURCE_BUNDLE}")
    text = FRAMER_SOURCE_BUNDLE.read_text(encoding="utf-8")
    pattern = rf"##\s+\d+\.\s+{re.escape(entry['filename'])}.*?```tsx\n(.*?)\n```"
    match = re.search(pattern, text, re.S)
    if not match:
        raise RuntimeError(f"Blocco TSX non trovato: {entry['filename']}")
    code = match.group(1)
    return code, hashlib.sha256(code.encode("utf-8")).hexdigest()


def _framer_bundle_format(entry: dict, code: str) -> tuple[str, str, str]:
    """Describe and fence the selected original source without translating it."""
    if entry.get("source_mode") == "native_archive":
        source = Path(entry["origin"]) / entry["source_file"]
        instructions = (
            "Questo e l'HTML SSR originale completo della pagina Framer e contiene "
            "il riferimento al modulo runtime originale. Estrai e integra la sola "
            "interazione selezionata conservando DOM, data-framer-*, CSS, asset e "
            "module URL originali. Isolala nella section esistente selezionata. "
            "Vietati iframe, screenshot, ricostruzioni GSAP, imitazioni o fallback."
        )
        return "html", str(source), instructions
    instructions = (
        "Questo e il componente React/TSX portabile verificato. Montalo realmente "
        "con script type=module/React, senza riscriverne fisica o struttura."
    )
    return "tsx", str(FRAMER_SOURCE_BUNDLE), instructions


# Regola generale: si usa tutto il catalogo, a rotazione. Sebastian (2026-07-22):
# "USALI TUTTI USA TUTTO, io non voglio semplicemente che abbiano tutti uguali".
# Non si scarta niente per gusto ne' per comodita'.
#
# Un solo motivo di esclusione resta ammesso: ZERO CONTENUTO SOSTITUIBILE, non
# estetica. Verificato sui sorgenti (Theodore-main/dist/index.html):
# `theodore-menu-transition` non ha NESSUN <img>, e il 100% del suo testo
# visibile sono le 8 voci del menu demo originale, hardcoded: "always / bold /
# casual / look / be / funky / mad / feelings" (nomi a caso di un fashion blog
# inglese). Con lo scheletro "copia esatta, non toccare" quel testo arriva
# letterale nel sito finale - e' il "non so cosa con una scritta" che Sebastian
# ha visto il 2026-07-25 (prova: heritage_winery_theodore_integration, sezione
# "La Galleria" seguita da quel testo). morphing-page-transition e
# outdoors-transition condividono lo stesso difetto: sono transizioni di
# pagina, non sezioni editoriali, oltre al problema di posizionamento
# (`position: fixed; top:0; width:100%; height:100vh`) gia' risolto da
# GUEST_CONTAINMENT_CSS per gli altri usi.
# Differenza da un'esclusione estetica: hover-grid e scroll-panels hanno
# anch'essi nomi demo placeholder nel testo, ma li' il contenuto visivo vero
# sono le immagini della griglia/gallery - qui non c'e' nessuna immagine da
# salvare la sezione.
#
# I 4 componenti con sorgenti TypeScript/TSX/SCSS restano inclusi: vengono
# compilati in JS/CSS statici da _transpile_component() (esbuild + sass,
# librerie lasciate esterne perche' gia' su CDN), e i 2 che sono componenti
# React puri montati via importmap da _assembled_react_guest_block(). La
# compilazione e' in cache su disco: durante un giro vero non parte npx.
EXCLUDED_FROM_FINE_DINING: set[str] = {
    "theodore-menu-transition",
    "morphing-page-transition",
    "outdoors-transition",
}

FINE_DINING_POOL = tuple(
    item for item in CATALOG if item["id"] not in EXCLUDED_FROM_FINE_DINING
)

# UN SOLO GUEST PER SITO (Sebastian, 2026-07-23: "troppi guest, troppi
# controlli"). L'export che funzionava davvero aveva un Guest solo; il secondo
# ha sempre prodotto duplicati o falsi e costava una fase in piu'. Il motore
# del Guest #2 resta nel codice: per riattivarlo basta questo flag.
SINGLE_GUEST = True

# SOLO FRAMER `portable_react`. I 10 `native_archive` sono interi siti Framer
# esportati: 165 KB, di cui 121 KB di CSS. Anche filtrando il CSS inutilizzato
# restano 142 KB — impossibili da incollare, ed e' il motivo per cui la Framer
# non compariva mai nel sito. I 3 portable_react sono componenti React da
# ~2,6 KB, e sono esattamente quelli che funzionavano nell'export del 16
# luglio. Meglio 3 che funzionano che 13 che spariscono.
FRAMER_POOL = tuple(
    item for item in FRAMER_CATALOG
    if item.get("source_mode", "portable_react") == "portable_react"
)

# Gabbia applicata alla root di OGNI Guest. `transform` e `filter` creano il
# containing block; `overflow: hidden` taglia gli sbordamenti; `isolation`
# impedisce agli z-index del componente di passare sopra il menu del sito.
GUEST_CONTAINMENT_CSS = """  /* GABBIA DI CONTENIMENTO - NON RIMUOVERE.
     Tiene il componente dentro la sua sezione: con un transform sulla root,
     ogni `position: fixed` interno si ancora a questa sezione e non al
     viewport, quindi il componente non puo' coprire il resto del sito. */
  #{root_id} {{
    position: relative;
    overflow: hidden;
    isolation: isolate;
    transform: translateZ(0);
    contain: layout paint;
    min-height: 100vh;
    z-index: 1;
  }}
  #{root_id} > * {{ max-width: 100%; }}
"""


def _least_used(items: tuple[dict, ...], counts: dict, previous: str | None, seed: int) -> dict:
    minimum = min(int(counts.get(item["id"], 0)) for item in items)
    candidates = [item for item in items if int(counts.get(item["id"], 0)) == minimum]
    alternatives = [item for item in candidates if item["id"] != previous]
    return (alternatives or candidates)[seed % len(alternatives or candidates)]


# Parametri per regia. Stessi effetti, numeri diversi: e' quello che impedisce
# ai siti di sembrare tutti uguali senza cambiare l'impianto. Tutti i valori
# sono tarati "fine dining": distanze corte, durate lunghe, ease senza rimbalzi.
#
# EASING (2026-07-27): i valori `ease` non sono piu' i built-in GSAP deboli
# (power2.out era "troppo debole", per usare le parole di Emil Kowalski). Sono
# tre curve CRAFTED registrate in cima al kit - kOut / kInOut / kDrawer - che
# corrispondono alle cubic-bezier di Emil quando il plugin CustomEase e'
# caricato, e ripiegano su built-in forti quando non c'e'. Ogni regia ne usa
# una diversa: cosi' le sei regie non si distinguono solo per COSA si muove,
# ma anche per COME - il carattere del movimento cambia, non solo i numeri.
_KIT_PARAMS = {
    "editorial-veil":       dict(clip="inset(0% 0% 100% 0%)", dur=1.4, y=34, ease="kOut",    par=8,  stag=0.09, scrub=1.0,
                                 fams=("curtain", "exit", "magnetic")),
    "cinematic-depth":      dict(clip="inset(12% 8% 12% 8%)", dur=1.6, y=42, ease="kInOut",  par=13, stag=0.07, scrub=1.2,
                                 fams=("pin", "blur", "magnetic")),
    "horizontal-narrative": dict(clip="inset(0% 100% 0% 0%)", dur=1.2, y=26, ease="kDrawer", par=6,  stag=0.06, scrub=0.8,
                                 fams=("drift", "counter", "magnetic")),
    "split-architecture":   dict(clip="inset(0% 0% 0% 100%)", dur=1.3, y=38, ease="kInOut",  par=10, stag=0.10, scrub=1.0,
                                 fams=("counter", "exit", "letters")),
    "quiet-luxury":         dict(clip="inset(0% 0% 100% 0%)", dur=1.8, y=22, ease="kDrawer", par=5,  stag=0.12, scrub=1.5,
                                 fams=("blur", "letters", "magnetic")),
    "gallery-drift":        dict(clip="inset(6% 4% 6% 4%)",   dur=1.5, y=30, ease="kOut",    par=14, stag=0.08, scrub=1.1,
                                 fams=("drift", "pin", "curtain")),
}


# FAMIGLIE MOTION VARIABILI.
#
# Fino al 2026-07-27 le sei regie cambiavano solo i NUMERI (durata, distanza,
# ease, percentuale di parallax): la coreografia era identica in tutte e sei,
# cioe' sempre reveal + titoli + parallax + scrub. Da fuori i siti sembravano
# tutti uguali, ed e' esattamente quello che Sebastian continuava a segnalare.
#
# Qui sotto c'e' un POOL di famiglie aggiuntive. Ogni regia ne pesca 3 (campo
# `fams` in _KIT_PARAMS), quindi due giri con regie diverse hanno una
# coreografia diversa, non solo un tempo diverso. Tutte guidate dallo scroll,
# tutte "fine dining": niente rimbalzi, niente rotazioni acrobatiche.
_FAMIGLIE_MOTION = {
    "drift": lambda p: f"""
/* DERIVA LATERALE — due colonne che scorrono a velocita' diverse. Da' la
   sensazione di profondita' senza muovere niente in verticale. */
gsap.utils.toArray('.mk-drift').forEach((el, i) => {{
  gsap.fromTo(el,
    {{ xPercent: i % 2 ? {p['par'] // 2 + 2} : -{p['par'] // 2 + 2} }},
    {{ xPercent: 0, ease: 'none',
      scrollTrigger: {{ trigger: el, start: 'top bottom', end: 'center center',
                       scrub: {p['scrub']} }} }});
}});""",
    "pin": lambda p: f"""
/* SEZIONE INCHIODATA — la sezione resta ferma mentre il suo contenuto avanza.
   E' il momento di regia piu' cinematografico: usalo UNA volta sola. */
gsap.utils.toArray('.mk-pin').forEach((el) => {{
  const dentro = el.querySelector('.mk-pin-move') || el.firstElementChild;
  if (!dentro) return;
  gsap.to(dentro, {{
    yPercent: -18, ease: 'none',
    scrollTrigger: {{ trigger: el, start: 'top top', end: '+=90%',
                     pin: true, scrub: {p['scrub']}, anticipatePin: 1 }}
  }});
}});""",
    "blur": lambda p: f"""
/* MESSA A FUOCO — il media entra leggermente sfocato e si mette a fuoco
   sullo scroll. Elegante perche' non muove niente: cambia solo la nitidezza. */
gsap.utils.toArray('.mk-blur').forEach((el) => {{
  const media = el.querySelector('img, video, picture') || el;
  gsap.fromTo(media,
    {{ filter: 'blur(14px)', scale: 1.06 }},
    {{ filter: 'blur(0px)', scale: 1, ease: 'none',
      scrollTrigger: {{ trigger: el, start: 'top 92%', end: 'center 60%',
                       scrub: {p['scrub']} }} }});
}});""",
    "curtain": lambda p: f"""
/* SIPARIO — un pannello del colore d'accento scorre via e scopre il media.
   Serve un figlio `.mk-curtain-panel` posizionato sopra il media. */
gsap.utils.toArray('.mk-curtain').forEach((el) => {{
  const panel = el.querySelector('.mk-curtain-panel');
  if (!panel) return;
  gsap.to(panel, {{
    scaleY: 0, transformOrigin: 'top center',
    duration: {p['dur']}, ease: '{p['ease']}',
    scrollTrigger: {{ trigger: el, start: 'top 78%' }}
  }});
}});""",
    "exit": lambda p: f"""
/* CONGEDO — la sezione si allontana mentre esce dallo schermo, invece di
   sparire di colpo. E' la meta' mancante di ogni "entrata": da' continuita'. */
gsap.utils.toArray('.mk-exit').forEach((el) => {{
  gsap.to(el, {{
    yPercent: -6, opacity: 0.35, scale: 0.97, ease: 'none',
    scrollTrigger: {{ trigger: el, start: 'bottom 70%', end: 'bottom top',
                     scrub: {p['scrub']} }}
  }});
}});""",
    "counter": lambda p: f"""
/* CONTROTEMPO — il testo sale mentre il media scende: le due meta' della
   sezione si muovono in direzioni opposte, agganciate allo scroll. */
gsap.utils.toArray('.mk-counter').forEach((el) => {{
  const testo = el.querySelector('.mk-counter-text');
  const media = el.querySelector('.mk-counter-media');
  if (!testo || !media) return;
  const st = {{ trigger: el, start: 'top bottom', end: 'bottom top',
               scrub: {p['scrub']} }};
  gsap.fromTo(testo, {{ yPercent: {p['par']} }}, {{ yPercent: -{p['par']}, ease: 'none', scrollTrigger: st }});
  gsap.fromTo(media, {{ yPercent: -{p['par'] // 2} }}, {{ yPercent: {p['par'] // 2}, ease: 'none', scrollTrigger: st }});
}});""",
    "magnetic": lambda p: f"""
/* CTA MAGNETICA — il bottone segue il cursore di pochi pixel e torna a posto.
   Unico effetto non guidato dallo scroll ammesso: e' una micro-risposta.
   In piu' (Emil Kowalski) scala a 0.97 alla pressione: da' feedback istantaneo,
   il bottone "sente" il click invece di restare inerte. */
gsap.utils.toArray('.mk-magnetic').forEach((btn) => {{
  btn.addEventListener('mousemove', (e) => {{
    const r = btn.getBoundingClientRect();
    gsap.to(btn, {{ x: (e.clientX - r.left - r.width / 2) * 0.22,
                   y: (e.clientY - r.top - r.height / 2) * 0.22,
                   duration: 0.4, ease: 'kOut' }});
  }});
  btn.addEventListener('mouseleave', () => {{
    gsap.to(btn, {{ x: 0, y: 0, scale: 1, duration: 0.6, ease: 'kDrawer' }});
  }});
  btn.addEventListener('mousedown', () => {{
    gsap.to(btn, {{ scale: 0.97, duration: 0.14, ease: 'kOut' }});
  }});
  btn.addEventListener('mouseup', () => {{
    gsap.to(btn, {{ scale: 1, duration: 0.2, ease: 'kOut' }});
  }});
}});""",
    "letters": lambda p: f"""
/* TITOLO LETTERA PER LETTERA — solo sul titolo firma della pagina.
   Dietro un controllo: se SplitText non c'e', il titolo resta visibile. */
if (typeof SplitText !== 'undefined') {{
  gsap.utils.toArray('.mk-letters').forEach((el) => {{
    const split = new SplitText(el, {{ type: 'chars' }});
    gsap.from(split.chars, {{
      yPercent: 100, opacity: 0, duration: {p['dur']}, ease: '{p['ease']}',
      stagger: {p['stag'] / 2},
      scrollTrigger: {{ trigger: el, start: 'top 85%' }}
    }});
  }});
}}""",
}

# Descrizione leggibile di ogni famiglia: serve per dire a Stitch DOVE
# applicare la classe, altrimenti la incolla e non la usa.
_USO_FAMIGLIE = {
    "drift": "`.mk-drift` -> colonne affiancate o card in fila (deriva laterale)",
    "pin": "`.mk-pin` -> UNA sola sezione, la piu' scenografica; il blocco che "
           "deve scorrere dentro va marcato `.mk-pin-move`",
    "blur": "`.mk-blur` -> un media grande (cantina, vigneto): entra sfocato e "
            "si mette a fuoco",
    "curtain": "`.mk-curtain` -> un media importante, con dentro un "
               "`<div class=\"mk-curtain-panel\">` del colore d'accento che lo "
               "copre e poi scorre via",
    "exit": "`.mk-exit` -> 2-3 sezioni intermedie: si congedano mentre escono",
    "counter": "`.mk-counter` -> una sezione testo+media affiancati; il testo "
               "`.mk-counter-text`, il media `.mk-counter-media`",
    "magnetic": "`.mk-magnetic` -> ogni bottone/CTA della pagina",
    "letters": "`.mk-letters` -> UN solo titolo, quello firma della pagina",
}


def _famiglie_variabili(p: dict) -> str:
    """Assembla le famiglie extra scelte da questa regia."""
    scelte = p.get("fams", ())
    blocchi = [_FAMIGLIE_MOTION[f](p) for f in scelte if f in _FAMIGLIE_MOTION]
    return "\n".join(blocchi) + "\n" if blocchi else ""


def _uso_famiglie(p: dict) -> str:
    """Elenco leggibile: dove va applicata ogni classe extra di questa regia."""
    righe = [f"- {_USO_FAMIGLIE[f]}" for f in p.get("fams", ()) if f in _USO_FAMIGLIE]
    return "\n".join(righe) if righe else "- (nessuna classe extra)"


def _motion_kit(style: dict) -> str:
    """Sistema di animazione GSAP gia' scritto, da incollare senza inventare.

    Stessa logica dello scheletro Guest: se Stitch deve PROGETTARE le
    animazioni, sceglie la strada piu' corta (roba al load, opacity e basta) e
    ci costa un giro di correzione, cioe' crediti. Se invece gliele consegniamo
    gia' scritte, incolla e il risultato e' quello voluto al primo colpo:
    tutto guidato dallo scroll, elegante, senza rimbalzi.
    """
    p = _KIT_PARAMS.get(style["id"], _KIT_PARAMS["quiet-luxury"])
    return f"""
## MOTION KIT GIA' SCRITTO — REGIA `{style['name']}` — E' IL PAVIMENTO, NON IL TETTO

Questo e' lo STRATO BASE del sistema di animazione, gia' tarato sulla regia
`{style['name']}` ({style['direction']}).

Incollalo INTEGRALMENTE e applica le sue classi agli elementi giusti: questo
strato non si riscrive, non si reinterpreta e non si sostituisce con roba tua.
Ogni suo effetto e' guidato dallo scroll: l'unica cosa che parte al
caricamento e' l'ingresso dell'hero, perche' e' gia' a schermo.

MA IL KIT DA SOLO NON BASTA. Dopo averlo incollato, ci scrivi SOPRA le tue
animazioni aggiuntive (pinning, scrub su X/Y, parallax asincrono tra colonne,
slittamenti e overlap), come richiesto nelle fasi precedenti di questo prompt.
Il kit garantisce il minimo su tutte le sezioni; la qualita' Awwwards la
aggiungi tu sopra. Le due cose convivono: non sono alternative.

### REGOLA CSS OBBLIGATORIA PER `.mk-parallax` — SENZA QUESTA SI VEDE UNA FASCIA VUOTA

Un'immagine che si muove dentro un contenitore della sua stessa altezza scopre
un bordo: sopra o sotto resta una striscia del colore di fondo. Nel sito del
2026-07-27 sotto il menu e' comparsa una fascia crema alta ~150px, ed era
esattamente questo: la foto della hero spinta in basso dal parallax.

Quindi il media dentro `.mk-parallax` deve essere PIU' ALTO del contenitore,
sempre, e il contenitore deve tagliare quello che esce:

```html
<div class="mk-parallax absolute inset-0 overflow-hidden">
  <img class="w-full object-cover"
       style="height:130%; position:absolute; top:-15%; left:0;" src="...">
</div>
```

130% di altezza con -15% in alto: il media puo' scorrere del {p['par']}% in
entrambe le direzioni senza mai scoprire un bordo. `overflow: hidden` sul
contenitore e' obbligatorio. Vale per OGNI `.mk-parallax` della pagina,
non solo per la hero.

Classi da applicare al markup:
- `.mk-reveal`   -> blocchi che compaiono entrando nel viewport (media, card, testo)
- `.mk-line`     -> ogni riga di titolo da rivelare
- `.mk-parallax` -> ogni immagine/video di sfondo
- `.mk-scrub`    -> media che si APRE progressivamente col dito sullo scroll
- `.mk-hero`     -> solo il contenuto della prima schermata

Classi SPECIFICHE di questa regia (cambiano a ogni sito: usale tutte e tre,
sono quello che rende questo sito diverso dal precedente):
{_uso_famiglie(p)}

VARIETA' OBBLIGATORIA: due sezioni adiacenti non devono mai usare lo stesso
effetto dominante. Alterna: una sezione a reveal, una a scrub, una a parallax.
Assegna `.mk-scrub` ad ALMENO 2 sezioni con media grandi (gallery, territorio,
cantina): sono i momenti di regia che fanno il "wow" Awwwards.

```html
<script id="stitch-motion-kit">
gsap.registerPlugin(ScrollTrigger);

/* 0. CURVE DI EASING CRAFTED (Emil Kowalski) — le built-in GSAP sono troppo
   deboli: mancano del carattere che rende un'animazione intenzionale. Qui
   registro tre curve col carattere giusto. Se il plugin CustomEase e'
   caricato uso le cubic-bezier esatte; se non c'e', ripiego su built-in forti
   con lo STESSO nome, cosi' il resto del kit funziona identico in entrambi i
   casi. `registerEase` e `parseEase` sono nel core GSAP, non serve plugin. */
if (typeof CustomEase !== 'undefined') {{
  gsap.registerPlugin(CustomEase);
  CustomEase.create('kOut',    '0.23, 1, 0.32, 1');     /* ease-out forte, editoriale */
  CustomEase.create('kInOut',  '0.77, 0, 0.175, 1');    /* ease-in-out drammatico */
  CustomEase.create('kDrawer', '0.32, 0.72, 0, 1');     /* glide morbido, lussuoso */
}} else {{
  gsap.registerEase('kOut',    gsap.parseEase('power4.out'));
  gsap.registerEase('kInOut',  gsap.parseEase('power4.inOut'));
  gsap.registerEase('kDrawer', gsap.parseEase('power3.out'));
}}

/* 1. SMOOTH SCROLL — dietro un controllo: se Lenis non carica, il resto del
   kit deve continuare a funzionare invece di morire su questa riga */
if (typeof Lenis !== 'undefined') {{
  const lenis = new Lenis({{ duration: 1.1, smoothWheel: true }});
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add((t) => lenis.raf(t * 1000));
  gsap.ticker.lagSmoothing(0);
}}

/* 2. HERO — UNICA animazione che parte al caricamento (e' gia' a schermo) */
gsap.from('.mk-hero', {{
  y: {p['y']}, opacity: 0, duration: {p['dur']}, ease: '{p['ease']}',
  stagger: {p['stag']}
}});

/* 3. REVEAL A MASCHERA — non semplice opacity: clip guidato dallo scroll.
   Parte da scale 0.96, non da scale 0: "niente nel mondo reale appare dal
   nulla" (Emil Kowalski). Anche una scala appena percettibile rende l'entrata
   naturale invece che teleportata. */
gsap.utils.toArray('.mk-reveal').forEach((el) => {{
  gsap.fromTo(el,
    {{ clipPath: '{p['clip']}', y: {p['y']}, opacity: 0, scale: 0.96 }},
    {{ clipPath: 'inset(0% 0% 0% 0%)', y: 0, opacity: 1, scale: 1,
      duration: {p['dur']}, ease: '{p['ease']}',
      scrollTrigger: {{ trigger: el, start: 'top 82%' }} }});
}});

/* 4. TITOLI RIGA PER RIGA */
gsap.utils.toArray('.mk-line').forEach((el) => {{
  gsap.from(el, {{
    yPercent: 110, opacity: 0, duration: {p['dur']}, ease: '{p['ease']}',
    stagger: {p['stag']},
    scrollTrigger: {{ trigger: el, start: 'top 88%' }}
  }});
}});

/* 5. PARALLAX — segue la posizione dello scroll (scrub).
   `fromTo` simmetrico, NON `to`: con `to` l'immagine parte gia' spostata
   (a pagina caricata il trigger e' gia' a meta' corsa) e scopre un bordo
   vuoto. Con -{p['par']} -> +{p['par']} il punto centrale e' zero. */
gsap.utils.toArray('.mk-parallax').forEach((el) => {{
  const media = el.querySelector('img, video, picture') || el;
  gsap.fromTo(media,
    {{ yPercent: -{p['par']} }},
    {{ yPercent: {p['par']}, ease: 'none',
      scrollTrigger: {{ trigger: el, start: 'top bottom', end: 'bottom top',
                       scrub: true }} }});
}});

/* 6. SCRUB CINEMATICO — il media si APRE col dito sullo scroll (momento wow).
   clip-path + scale legati alla POSIZIONE dello scroll, non al tempo: e' la
   regia Awwwards che chiedi, elegante perche' scrub e non fade. */
gsap.utils.toArray('.mk-scrub').forEach((el) => {{
  const media = el.querySelector('img, video, picture, canvas') || el;
  gsap.fromTo(media,
    {{ clipPath: '{p['clip']}', scale: 1.18 }},
    {{ clipPath: 'inset(0% 0% 0% 0%)', scale: 1, ease: 'none',
      scrollTrigger: {{ trigger: el, start: 'top 90%', end: 'center center',
                       scrub: {p['scrub']} }} }});
}});

{_famiglie_variabili(p)}
/* RISPETTO DELLE PREFERENZE UTENTE */
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {{
  ScrollTrigger.getAll().forEach((t) => t.kill());
  gsap.set('.mk-reveal, .mk-line, .mk-hero, .mk-scrub, .mk-scrub img, .mk-scrub video, '
         + '.mk-drift, .mk-blur, .mk-blur img, .mk-exit, .mk-counter-text, '
         + '.mk-counter-media, .mk-letters, .mk-curtain-panel, .mk-pin-move',
           {{ clearProps: 'all', opacity: 1 }});
}}

window.addEventListener('load', () => ScrollTrigger.refresh());
</script>
```

REGOLE SUL KIT:
1. Incollalo una volta sola, integralmente.
2. Applica le classi a TUTTE le sezioni: una sezione senza `.mk-reveal` resta
   ferma ed e' un errore.
3. Puoi AGGIUNGERE animazioni tue, ma ognuna deve avere `scrollTrigger`.
   Nessuna animazione al caricamento oltre a `.mk-hero`.
4. Eleganza obbligatoria: niente rimbalzi (`bounce`, `elastic`, `back`), niente
   rotazioni acrobatiche, niente durate sotto 0.6s. Sono ristoranti stellati.
5. VIETATO nascondere il contenuto dal CSS "in attesa" dell'animazione.
   Righe come `.mk-line, .mk-hero {{ opacity: 0; }}` in un `<style>` sono
   VIETATE. Il kit usa `gsap.from()`, che parte da solo dallo stato nascosto:
   se GSAP non carica il testo resta VISIBILE invece di sparire. Se aggiungi
   `opacity: 0` nel CSS distruggi questa protezione e un solo script mancante
   ti svuota la pagina. E' successo il 2026-07-27: hero e titoli invisibili.
6. Ogni plugin non-core va dietro `typeof X !== 'undefined'`. Il kit qui sopra
   usa solo ScrollTrigger e (protetto) Lenis: se aggiungi SplitText o Flip,
   proteggili allo stesso modo e prevedi il ripiego senza plugin.
"""


def _motion_contract(
    component: dict,
    component2: dict | None,
    framer: dict,
    style: dict,
    component_hashes: dict[str, str],
    component2_hashes: dict[str, str],
    framer_hash: str,
) -> str:
    roles = "logo, nav, title, body, media, caption, cta, icon, control, footer"
    guest_hashes = json.dumps(sorted(component_hashes.values()))
    framer_execution = (
        f"preserva il DOM SSR e il modulo runtime originale `{framer['module_url']}`"
        if framer.get("source_mode") == "native_archive"
        else "monta il componente React/TSX con `<script type=\"module\">`"
    )
    guest2_riga = (
        f"- Guest Component #2: `{component2['name']}` (`{component2['id']}`)\n"
        if component2 else ""
    )
    guest2_firma = (
        f'<div data-stitch-native-component="{component2["id"]}"\n'
        f'     data-motion-component="{component2["dom_value"]}"\n'
        f'     data-motion-activation="scroll"\n'
        f'     data-motion-mounted="false"></div>\n'
        if component2 else ""
    )
    guest2_vars = (
        f'window.__STITCH_SELECTED_COMPONENT_2__ = "{component2["id"]}";\n'
        f"window.__STITCH_GUEST_2_SOURCE_SHA256__ = "
        f"{json.dumps(sorted(component2_hashes.values()))};\n"
        if component2 else ""
    )
    guest2_mount = (
        f"Applica lo stesso contratto separato a `{component2['function']}`\n"
        f"per il Guest #2: un secondo gate, una seconda root e nessuna invocazione eager.\n"
        if component2 else ""
    )
    quanti = "quattro" if component2 else "tre"
    coesistenza = (
        "Entrambi i Guest e la Framer devono esistere una sola volta. I due Guest devono\n"
        "occupare due nuove sezioni distinte e non adiacenti, senza sostituire sezioni reference."
        if component2 else
        "Il Guest e la Framer devono esistere una sola volta. Il Guest occupa una nuova\n"
        "sezione in piu', senza sostituire sezioni reference."
    )
    return f"""
## ASSIGNMENT BLOCCANTE

- Guest Component #1: `{component['name']}` (`{component['id']}`)
{guest2_riga}- Framer Interactive: `{framer['name']}` (`{framer['id']}`)
- Regia GSAP: `{style['name']}` (`{style['id']}`): {style['direction']}.

I {quanti} file allegati sono sorgenti eseguibili, non ispirazione. Integra codice,
DOM e matematica originali. Vietati riassunti, surrogati, adapter vuoti e TODO.
{coesistenza}
Ogni Guest deve restare inattivo al caricamento iniziale e montarsi una sola volta
esclusivamente da `ScrollTrigger.create({{ onEnter: ... }})` oppure dal callback
`IntersectionObserver` quando `entry.isIntersecting === true`. Sono vietate chiamate
dirette al mount a livello globale, in `DOMContentLoaded`, `load`, `setTimeout` o
`setInterval`. L'unica eccezione e un componente nativo CSS scroll-driven che usa
realmente `animation-timeline`, `scroll-timeline` o `view-timeline`.

OBBLIGO DI COPERTURA:
- ogni sezione ha entrata, progressione durante lo scroll e uscita;
- ogni elemento significativo riceve `data-motion-role`: {roles};
- usa almeno sei valori distinti di `data-motion-family`;
- ogni `<section>` riceve `data-motion-section`, `data-motion-entry`,
  `data-motion-traverse` e `data-motion-exit`;
- menu, CTA e controlli restano funzionanti e il layout non cambia.

MENU GLOBALE OBBLIGATORIO:
- root con `data-stitch-transparent-nav="true"` e `data-scroll-visibility="top-only"`;
- in cima e visibile, completamente trasparente e privo di fondo, blur, bordo e ombra;
- logo e link testuali allineati su una sola linea e centrati verticalmente;
- dopo 48-96 px scompare verso l'alto e ritorna solo nella zona iniziale;
- funzione reale `initTransparentScrollNav()` indipendente dal gate scroll Guest.

Firme obbligatorie:
```html
<div data-stitch-native-component="{component['id']}"
     data-motion-component="{component['dom_value']}"
     data-motion-activation="scroll"
     data-motion-mounted="false"></div>
{guest2_firma}<div data-stitch-framer-interaction="{framer['id']}"
     data-motion-framer="{framer['dom_value']}"></div>
<script>
window.__STITCH_SELECTED_COMPONENT__ = "{component['id']}";
{guest2_vars}window.__STITCH_SELECTED_FRAMER__ = "{framer['id']}";
window.__STITCH_MOTION_STYLE__ = "{style['id']}";
window.__STITCH_MOTION_MANIFEST__ = "arsenal-v7.1";
window.__STITCH_GUEST_SOURCE_SHA256__ = {guest_hashes};
window.__STITCH_FRAMER_SOURCE_SHA256__ = "{framer_hash}";
</script>
```

Definisci realmente `{component['function']}`, ma invocala soltanto dal gate di
scroll descritto sopra. Nel callback, dopo il mount riuscito, imposta
`data-motion-mounted="true"`; usa un guard booleano o questo attributo per impedire
mount duplicati. {guest2_mount}Per la Framer,
{framer_execution}; definisci e invoca realmente `{framer['function']}` come
wrapper di inizializzazione isolato, senza simulazioni o sostituzioni.
{_motion_kit(style)}
""".strip()


def _final_audit(
    component: dict,
    component2: dict | None,
    framer: dict,
    style: dict,
    component_hashes: dict[str, str],
    component2_hashes: dict[str, str],
    framer_hash: str,
) -> str:
    guest_hashes = ", ".join(sorted(component_hashes.values()))
    guest2_righe = (
        f"- una seconda root Guest `{component2['id']}` distinta, con funzione\n"
        f"  `{component2['function']}` invocata una sola volta dal proprio gate scroll;\n"
        f"- hash Guest #2 dichiarati: `{', '.join(sorted(component2_hashes.values()))}`;\n"
        if component2 else ""
    )
    return f"""

AUDIT SELEZIONE BLOCCANTE:
- una root Guest `{component['id']}` con `data-motion-activation="scroll"`;
- funzione `{component['function']}` definita e invocata una sola volta esclusivamente
  da `ScrollTrigger.onEnter` o `IntersectionObserver`; nessuna inizializzazione eager;
{guest2_righe}- una root Framer `{framer['id']}`, componente `{framer['function']}` montato e invocato;
- manifesto `arsenal-v7.1` e regia `{style['id']}` presenti;
- hash Guest dichiarati: `{guest_hashes}`;
- hash Framer dichiarato: `{framer_hash}`;
- almeno sei famiglie motion; ogni sezione ha entry/traverse/exit;
- ruoli motion su logo, nav, titoli, testo, media, caption, CTA, icone, controlli e footer;
- nessun errore console, overflow, immagine rotta, contenuto invisibile o link/menu inattivo.
- menu trasparente e allineato in cima, nascosto dopo lo scroll, senza attivare il Guest;
Correggi fisicamente prima di terminare. Non ridisegnare il sito.
"""


_NEEDS_BUILD_SUFFIXES = {".ts", ".tsx", ".jsx", ".scss", ".sass", ".vue"}

# Testi della cornice-demo Codrops: se finiscono nel sito, il cliente legge
# "Previous demo" o il nome del componente dentro il sito del suo ristorante.
_DEMO_CHROME_TEXT = re.compile(
    r"previous demo|next demo|all demos|back to the article|"
    r"codrops|made by|follow us|article on|view all",
    re.I,
)
# Contenitori standard della cornice-demo. In tutti i progetti Codrops la barra
# con titolo/link sta in `.frame` (e derivati BEM `frame__*`); il componente
# vero vive in `.content`, `.grid`, `.slideshow` ecc.
_DEMO_CHROME_CLASS = re.compile(
    # `outro`, `card-wrap` e `card__*` sono il blocco finale "More you might
    # like" con i link a tympanus.net: nel sito del cliente compariva come una
    # gallery di altre demo Codrops (visto nell'export del 2026-07-25).
    r"^(frame|codrops|cdawrap|demos?|demo-nav|credits|outro|card-wrap|card)(__|-|$)",
    re.I,
)


def _mark_demo_text(body) -> int:
    """Marca i testi-segnaposto della demo perche' Stitch li sostituisca.

    I componenti Codrops portano dentro il copy del loro demo: one-element-scroll
    parla di "Seraph Kamos", "Natural Garments", "organic cotton", "wool from
    sheep" - il catalogo di un marchio di abbigliamento, finito dentro il sito
    di una cantina (export del 2026-07-25).

    Non si puo' riempirlo da Python: il contenuto giusto sta nelle reference,
    che le vede solo Stitch. Ma glielo si puo' rendere un lavoro minimo e
    inequivocabile - "sostituisci il testo di questi tag" - invece di lasciarlo
    alla sua iniziativa. La struttura, le classi e i nodi restano identici,
    quindi le animazioni originali continuano a funzionare.
    """
    marcati = 0
    for elemento in body.find_all(["h1", "h2", "h3", "h4", "p", "span", "strong", "li"]):
        # Solo i nodi foglia con testo proprio: evita di marcare i contenitori.
        if elemento.find(True):
            continue
        testo = (elemento.get_text() or "").strip()
        if len(testo) < 3:
            continue
        elemento["data-stitch-fill"] = "true"
        marcati += 1
    return marcati


def _scope_component_css(css: str, root_id: str) -> str:
    """Confina il CSS del componente dentro la sua sezione.

    Il base.css dei componenti Codrops stila `body`, `html` e `:root`: incollato
    tale e quale, riscrive lo sfondo, il font e le variabili colore DI TUTTO IL
    SITO. Nell'export del 2026-07-25 il `body { font-family: "capitana";
    background-image: url(...); background-attachment: fixed }` di
    one-element-scroll si e' applicato all'intera pagina della cantina.
    Qui quei selettori diventano `#guest-N-<id>`, cosi' le stesse regole
    valgono solo dentro la sezione del componente.
    """
    def riscrivi_selettore(selettore: str) -> str:
        # I commenti CSS che precedono la regola (`/* --- base.css --- */`)
        # vanno tenuti da parte: attaccati al selettore impedirebbero di
        # riconoscere `:root` o `html` e la regola resterebbe globale.
        commenti = "".join(re.findall(r"/\*.*?\*/", selettore, re.S))
        selettore = re.sub(r"/\*.*?\*/", "", selettore, flags=re.S)
        prefisso = (commenti + "\n") if commenti else ""
        pezzi = []
        for pezzo in selettore.split(","):
            testa = pezzo.strip()
            if not testa:
                continue
            # `html`, `body`, `:root` — da soli o con classe/stato attaccati
            # (`html.js`, `body.loading`) — diventano la root della sezione.
            if re.fullmatch(r"(?:html|body|:root)(?:[.:#\[][^\s>+~]*)?", testa, re.I):
                pezzi.append(f"#{root_id}")
            elif re.match(r"(?:html|body|:root)\b", testa, re.I):
                # discendenti: `body .x`, `html.js .y` -> `#root .x`
                pezzi.append(re.sub(r"^(?:html|body|:root)[^\s>+~]*", f"#{root_id}", testa, flags=re.I))
            else:
                pezzi.append(testa)
        # `html, body` nella stessa regola collassano sullo stesso id: deduplica.
        visti, unici = set(), []
        for p in pezzi:
            if p not in visti:
                visti.add(p)
                unici.append(p)
        return prefisso + ", ".join(unici)

    # Parser a scansione: piu' robusto di un regex, perche' i reset CSS hanno
    # selettori su piu' righe (`html, body, div, span,\n applet, object {`) che
    # un regex ancorato a fine riga spezzerebbe a meta'.
    fuori = []
    selettore = []
    profondita = 0
    indice = 0
    while indice < len(css):
        carattere = css[indice]
        if profondita > 0:
            # Dentro un blocco: copia tutto finche' non si chiude.
            fuori.append(carattere)
            if carattere == "{":
                profondita += 1
            elif carattere == "}":
                profondita -= 1
                if profondita == 0:
                    selettore = []
            indice += 1
            continue
        if carattere == "{":
            testo = "".join(selettore)
            # Le at-rule (@media, @supports) mantengono il loro prologo e i
            # selettori interni vengono riscritti dal giro successivo.
            if testo.lstrip().startswith("@"):
                if re.match(r"\s*@(?:media|supports|layer|container)", testo, re.I):
                    fuori.append(testo + "{")  # apre: continuiamo a profondita' 0
                else:
                    fuori.append(testo + "{")
                    profondita = 1
            else:
                fuori.append(riscrivi_selettore(testo) + " {")
                profondita = 1
            selettore = []
            indice += 1
            continue
        if carattere == "}":
            fuori.append("}")
            selettore = []
            indice += 1
            continue
        if carattere == ";":
            # Statement senza blocco (`@import url(...);`, `@charset "...";`).
            # Va scaricato subito, altrimenti resta incollato al selettore che
            # segue e lo fa sembrare parte di un'at-rule: la regola successiva
            # non verrebbe confinata.
            fuori.append("".join(selettore) + ";")
            selettore = []
            indice += 1
            continue
        selettore.append(carattere)
        indice += 1
    fuori.append("".join(selettore))
    return "".join(fuori)


def _strip_demo_chrome(body) -> None:
    """Toglie la cornice della demo Codrops dal markup del componente.

    Senza questo, nel sito del ristorante compaiono come testo visibile
    "Previous demo", "Back to the article" e il NOME del componente: e' la
    pagina-vetrina di Codrops incollata dentro il sito del cliente.
    Verificato: 18 componenti su 31 la portavano dentro.
    """
    for element in list(body.find_all(True)):
        if not element.parent:
            continue  # gia' rimosso con un antenato
        classi = " ".join(element.get("class") or [])
        if any(_DEMO_CHROME_CLASS.match(c) for c in (element.get("class") or [])):
            element.decompose()
            continue
        # Link/blocchi residui il cui testo E' soltanto una frase di cornice.
        testo = " ".join((element.get_text(" ", strip=True) or "").split())
        if testo and len(testo) < 60 and _DEMO_CHROME_TEXT.fullmatch(testo.strip(" .·|—-")):
            element.decompose()
# ---------------------------------------------------------------------------
# FOTO DEL COMPONENTE (Stadio 1 di 2)
#
# Il componente Codrops E' le sue foto: one-element-scroll e' un unico
# elemento-foto che si trasforma lungo lo scroll; tolta l'immagine non e'
# impoverito, non esiste. Consegnato a Stitch con `url(img/1.jpg)` (percorsi
# che nell'export non esistono), Stitch li riempie con foto IA riciclate: e'
# la causa vera del "non c'entra un cazzo con l'originale".
#
# Qui, Stadio 1: ogni foto diventa una variabile CSS (o un data URI su <img>)
# con un'ANTEPRIMA leggera della foto ORIGINALE, cosi' Stitch vede la
# composizione giusta e non ha slot da inventare. Il manifest registra
# variabile -> file originale; lo Stadio 2 (download_stitch_project.py)
# ripristina la piena risoluzione dopo il download.
# ---------------------------------------------------------------------------

# Manifest immagini accumulato mentre si costruiscono i bundle Guest.
# prepare_motion_selection lo azzera all'inizio e lo scrive su disco alla fine.
# Struttura: { root_id: { var_o_marker: {"file", "name", "kind": "var"|"src"} } }
_GUEST_IMAGE_MANIFEST: dict[str, dict[str, dict]] = {}

_IMG_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg"}


def _resolve_component_asset(source_root: Path, ref: str) -> Path | None:
    """Risolve un riferimento immagine relativo al file reale del componente."""
    ref = (ref or "").strip().strip("'\"").strip()
    if not ref or ref.startswith(("data:", "http:", "https:", "//", "#")):
        return None
    ref = ref.split("?", 1)[0].split("#", 1)[0]
    name = Path(ref).name
    if Path(name).suffix.lower() not in _IMG_SUFFIXES:
        return None
    root_resolved = source_root.resolve()
    # I percorsi sono relativi all'index.html (`img/1.jpg`) o al css (`../img/x`).
    for base in (source_root, source_root / "css", source_root / "js", source_root / "img"):
        try:
            resolved = (base / ref).resolve()
        except (OSError, ValueError, RuntimeError):
            continue
        if resolved.is_file() and root_resolved in resolved.parents:
            return resolved
    for found in source_root.rglob(name):
        if found.is_file():
            return found
    return None


def _lqip_data_uri(path: Path, max_side: int = 48) -> str:
    """LQIP minuscolo (data URI) dalla foto originale: ~1 KB, solo anteprima."""
    # Gli SVG sono vettoriali: niente da rasterizzare, si incorpora il file
    # intero (di solito e' una piccola grafica decorativa di sfondo).
    if path.suffix.lower() == ".svg":
        try:
            raw = path.read_bytes()
            encoded = base64.b64encode(raw).decode("ascii")
            return f"data:image/svg+xml;base64,{encoded}"
        except Exception:
            return (
                "data:image/gif;base64,"
                "R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
            )
    try:
        from PIL import Image, ImageFilter

        with Image.open(path) as im:
            has_alpha = im.mode in ("RGBA", "LA", "PA") or (
                im.mode == "P" and "transparency" in im.info
            )
            im = im.convert("RGBA" if has_alpha else "RGB")
            im.thumbnail((max_side, max_side))
            im = im.filter(ImageFilter.GaussianBlur(1.2))
            buffer = io.BytesIO()
            if has_alpha:
                im.save(buffer, format="PNG", optimize=True)
                mime = "image/png"
            else:
                im.save(buffer, format="JPEG", quality=32)
                mime = "image/jpeg"
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except Exception:
        # 1x1 trasparente: non rompe mai il layout, caso peggiore = slot vuoto.
        return (
            "data:image/gif;base64,"
            "R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
        )


def _inline_component_images(
    body, css: str, component: dict, slot: int, root_id: str
) -> tuple[str, str]:
    """Stadio 1: rimpiazza le foto del componente con anteprime + variabili.

    Muta `body` (BeautifulSoup) in place per gli `<img src>` e gli style inline,
    riscrive gli `url()` nel `css`, registra il manifest e ritorna
    `(css, blocco_variabili_da_mettere_nella_root)`.
    """
    source_root = Path(component["source_root"])
    assigned: dict[str, str] = {}       # file assoluto -> nome variabile
    declarations: list[str] = []        # righe `--var: url(lqip);`
    manifest: dict[str, dict] = _GUEST_IMAGE_MANIFEST.setdefault(root_id, {})
    counter = {"n": len(assigned)}

    def registra(resolved: Path, kind: str) -> str:
        key = str(resolved)
        var = assigned.get(key)
        if var is None:
            counter["n"] += 1
            var = f"g{slot}img-{counter['n']}"
            assigned[key] = var
            if kind == "var":
                declarations.append(f"    --{var}: url({_lqip_data_uri(resolved)});")
            manifest[var] = {
                "file": key,
                "name": f"{var}{resolved.suffix.lower()}",
                "kind": kind,
            }
        return var

    url_pattern = re.compile(r"url\(\s*(['\"]?[^)'\"]+['\"]?)\s*\)")

    def sostituisci_url(match: "re.Match[str]") -> str:
        resolved = _resolve_component_asset(source_root, match.group(1))
        if resolved is None:
            return match.group(0)  # font, @import, mask #id, http: lasciali stare
        return f"var(--{registra(resolved, 'var')})"

    # 1) style inline nel markup: `style="background-image:url(img/1.jpg)"`.
    for el in body.find_all(style=True):
        style = el.get("style") or ""
        if "url(" in style:
            el["style"] = url_pattern.sub(sostituisci_url, style)

    # 2) <img src="img/1.jpg">: src non accetta var(), quindi mettiamo il LQIP
    #    direttamente e marchiamo l'elemento perche' lo Stadio 2 lo ritrovi.
    for img in body.find_all("img", src=True):
        resolved = _resolve_component_asset(source_root, img.get("src", ""))
        if resolved is None:
            continue
        var = registra(resolved, "src")
        img["src"] = _lqip_data_uri(resolved)
        img["data-guest-img"] = var
        if img.has_attr("srcset"):
            del img["srcset"]  # altrimenti il browser preferisce lo srcset morto

    # 3) url() nel CSS del componente (`body { background: url(../img/noise.png) }`).
    css = url_pattern.sub(sostituisci_url, css)

    if not manifest:
        _GUEST_IMAGE_MANIFEST.pop(root_id, None)
    var_block = ""
    if declarations:
        var_block = (
            "  /* FOTO ORIGINALI DEL COMPONENTE — NON TOCCARE QUESTE VARIABILI.\n"
            "     Sono le vere immagini del componente (anteprima leggera).\n"
            "     Non sostituirle, non rimuoverle, non rinominarle. */\n"
            f"  #{root_id} {{\n" + "\n".join(declarations) + "\n  }\n"
        )
    return css, var_block


TRANSPILED_DIR = GENERATED_DIR / "_transpiled"

# Le librerie sono gia' globali sulla pagina (CDN). Il codice compilato le
# cerca con require(): questo shim gliele consegna dal window.
_REQUIRE_SHIM = """(function(require){
%s
})(function(name){
  if (name === "gsap" || name.endsWith("/gsap")) return { gsap: window.gsap, default: window.gsap };
  if (name.indexOf("ScrollTrigger") >= 0) return { ScrollTrigger: window.ScrollTrigger, default: window.ScrollTrigger };
  if (name.indexOf("ScrollSmoother") >= 0) return { ScrollSmoother: window.ScrollSmoother, default: window.ScrollSmoother };
  if (name.indexOf("Flip") >= 0) return { Flip: window.Flip, default: window.Flip };
  if (name.indexOf("Draggable") >= 0) return { Draggable: window.Draggable, default: window.Draggable };
  if (name === "lenis" || name.indexOf("lenis") >= 0) return { default: window.Lenis };
  return {};
});"""


def _run(cmd: list[str], timeout: int = 240) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def _transpile_component(component: dict) -> tuple[str, str] | None:
    """Compila TypeScript/TSX/SCSS in JS e CSS statici, con cache su disco.

    Serve per i componenti che non sono HTML statico: senza compilarli non
    girerebbero mai in un export Stitch, e nessun prompt puo' cambiarlo -
    il browser non esegue TypeScript. Usa esbuild e sass via npx.
    Ritorna (js, css) oppure None se la compilazione non riesce.
    """
    paths = _source_paths(component)
    entry = next(
        (p for p in paths if p.suffix.lower() in {".ts", ".tsx", ".jsx"}
         and p.stem.lower() in {"main", "index", "app", "script"}),
        None,
    ) or next((p for p in paths if p.suffix.lower() in {".ts", ".tsx", ".jsx"}), None)
    scss = [p for p in paths if p.suffix.lower() in {".scss", ".sass"}]
    if entry is None and not scss:
        return None

    cache = TRANSPILED_DIR / component["id"]
    js_out, css_out = cache / "bundle.js", cache / "bundle.css"
    newest = max((p.stat().st_mtime for p in paths), default=0)
    if js_out.is_file() and js_out.stat().st_mtime >= newest:
        return (
            js_out.read_text(encoding="utf-8"),
            css_out.read_text(encoding="utf-8") if css_out.is_file() else "",
        )
    cache.mkdir(parents=True, exist_ok=True)

    js = ""
    if entry is not None:
        # Le librerie restano ESTERNE: sono gia' sulla pagina via CDN. Senza
        # questi flag esbuild se le incorpora e il bundle passa da 5 KB a 350 KB.
        code, out, err = _run([
            "npx", "--yes", "esbuild", str(entry), "--bundle", "--format=iife",
            "--external:gsap", "--external:gsap/*", "--external:@gsap/react",
            "--external:react", "--external:react/*",
            "--external:react-dom", "--external:react-dom/*",
            "--external:lenis", "--external:*.css", "--external:*.scss",
            "--loader:.ts=ts", "--loader:.tsx=tsx", "--loader:.jsx=jsx",
            "--jsx=automatic",
        ])
        if code != 0:
            print(f"  transpile fallito per {component['id']}: {err.strip()[:160]}")
            return None
        js = _REQUIRE_SHIM % out

    css_parts = []
    for source in scss:
        code, out, err = _run(["npx", "--yes", "sass", "--no-source-map", str(source)])
        if code == 0:
            css_parts.append(f"/* --- {source.name} (da SCSS) --- */\n{out}")
        else:
            print(f"  sass fallito per {source.name}: {err.strip()[:120]}")
    css = "\n".join(css_parts)

    js_out.write_text(js, encoding="utf-8")
    css_out.write_text(css, encoding="utf-8")
    return js, css


def _assembled_react_guest_block(
    component: dict, slot: int, source_hashes: dict[str, str], css: str
) -> str | None:
    """Blocco per i Guest che sono componenti React puri (solo .tsx).

    Compilati in ESM e montati via importmap, esattamente come fa gia' la
    Framer `portable_react` che nell'export del 16 luglio funzionava.
    """
    entry = next(
        (p for p in _source_paths(component)
         if p.suffix.lower() in {".tsx", ".jsx"}
         and p.stem.lower() in {"app", "main", "index"} or p.suffix.lower() == ".tsx"),
        None,
    )
    if entry is None:
        return None
    code, esm, err = _run([
        "npx", "--yes", "esbuild", str(entry), "--bundle", "--format=esm",
        "--external:react", "--external:react/*",
        "--external:react-dom", "--external:react-dom/*",
        "--external:gsap", "--external:gsap/*", "--external:@gsap/react",
        "--external:*.css", "--external:*.scss",
        "--loader:.tsx=tsx", "--loader:.jsx=jsx", "--jsx=automatic",
    ])
    if code != 0:
        print(f"  build React fallita per {component['id']}: {err.strip()[:140]}")
        return None

    # esbuild chiude con `export { Nome as default };`: lo rimuoviamo e ci
    # teniamo il nome locale, che non coincide sempre con quello del catalogo.
    match = re.search(r"export\s*\{([^}]*)\}\s*;?\s*$", esm)
    local = None
    if match:
        for pezzo in match.group(1).split(","):
            if "as default" in pezzo:
                local = pezzo.split("as")[0].strip()
        esm = esm[:match.start()]
    if not local:
        return None

    suffix = "" if slot == 1 else "_2"
    root_id = f"guest-{slot}-{component['id']}"
    hash_lines = ",\n".join(
        f'    "{name}": "{digest}"' for name, digest in sorted(source_hashes.items())
    )
    return (
        f"```html\n"
        f'<section id="{root_id}"\n'
        f'         data-stitch-native-component="{component["id"]}"\n'
        f'         data-motion-component="{component["dom_value"]}"\n'
        f'         data-motion-activation="scroll"\n'
        f'         data-motion-mounted="false">\n'
        f"  <style>\n"
        f"{GUEST_CONTAINMENT_CSS.format(root_id=root_id)}"
        f"{css}\n"
        f"  </style>\n"
        f'  <div id="{root_id}-react"></div>\n'
        f"</section>\n"
        f'<script type="module">\n'
        f"import React from 'react';\n"
        f"import {{ createRoot }} from 'react-dom/client';\n"
        f'window.__STITCH_SELECTED_COMPONENT{suffix}__ = "{component["id"]}";\n'
        f"window.__STITCH_GUEST{suffix}_SOURCE_SHA256__ = {{\n{hash_lines}\n}};\n"
        f"{esm}\n"
        f"function {component['function']}() {{\n"
        f'  const root = document.getElementById("{root_id}");\n'
        f'  if (!root || root.dataset.motionMounted === "true") return;\n'
        f'  root.dataset.motionMounted = "true";\n'
        f"  gsap.from(root, {{\n"
        f'    opacity: 0, duration: 0.9, ease: "power3.out",\n'
        f'    scrollTrigger: {{ trigger: root, start: "top 85%" }}\n'
        f"  }});\n"
        f'  createRoot(document.getElementById("{root_id}-react"))'
        f".render(React.createElement({local}));\n"
        f"}}\n"
        # Doppio innesco: ScrollTrigger se c'e', altrimenti IntersectionObserver.
        # Cosi' il mount a scroll non dipende dall'ordine di caricamento di GSAP.
        f"(function(){{\n"
        f"  const fire = () => {component['function']}();\n"
        f"  if (window.ScrollTrigger) {{\n"
        f"    ScrollTrigger.create({{\n"
        f'      trigger: "#{root_id}", start: "top 85%",\n'
        f"      once: true, onEnter: fire\n"
        f"    }});\n"
        f"  }} else {{\n"
        f"    new IntersectionObserver((entries, obs) => {{\n"
        f"      entries.forEach((entry) => {{\n"
        f"        if (entry.isIntersecting) {{ fire(); obs.disconnect(); }}\n"
        f"      }});\n"
        f'    }}, {{ rootMargin: "0px 0px -15% 0px" }}\n'
        f'    ).observe(document.getElementById("{root_id}"));\n'
        f"  }}\n"
        f"}})();\n"
        f"</script>\n"
        f"```\n"
    )


def _assembled_guest_block(component: dict, slot: int, source_hashes: dict[str, str]) -> str | None:
    """Blocco Guest GIA' MONTATO: CSS, markup e JS originali gia' al loro posto.

    Ultimo pezzo di lavoro che restava a Stitch: prendere i sorgenti sparsi e
    incastrarli nei buchi dello scheletro. Anche quello e' lavoro, quindi anche
    quello lo salta. Qui il montaggio lo facciamo noi in Python e gli
    consegniamo UN blocco da copiare tale e quale: niente da assemblare,
    niente da decidere, nessuna via di scampo.

    Ritorna None se il componente ha sorgenti che vanno compilati (TypeScript,
    SCSS, TSX): quelli non si possono montare verbatim in una pagina statica e
    restano sullo scheletro a buchi, con l'istruzione esplicita di convertirli.
    """
    from bs4 import BeautifulSoup, Comment

    paths = [p for p in _source_paths(component) if _is_injectable_source(p)]
    if not paths:
        return None

    # Sorgenti da compilare (TS/TSX/SCSS): li trasformiamo in JS e CSS statici
    # invece di scaricare il problema su Stitch, che non potrebbe risolverlo.
    built_js = built_css = ""
    if any(p.suffix.lower() in _NEEDS_BUILD_SUFFIXES for p in paths):
        # Compilazione TS/TSX/SCSS -> JS/CSS statici. Il risultato e'
        # messo in cache su disco da _transpile_component, quindi durante
        # un giro vero non viene eseguito nessun comando esterno.
        transpiled = _transpile_component(component)
        if not transpiled:
            return None
        built_js, built_css = transpiled

    index = next((p for p in paths if p.name.lower() == "index.html"), None)
    if index is None:
        # Componente React puro: niente index.html da cui estrarre il markup,
        # perche' il markup lo produce il componente stesso. Si monta come fa
        # gia' la Framer portable_react, usando l'importmap React/GSAP che
        # l'export Stitch espone.
        return _assembled_react_guest_block(component, slot, source_hashes, built_css)

    soup = BeautifulSoup(index.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    body = soup.body
    if body is None:
        return None
    # I <script src> puntano ai file locali che stiamo gia' inlinando qui sotto.
    for tag in body.find_all("script"):
        tag.decompose()
    # I COMMENTI VANNO TOLTI, non lasciati: `str(Comment)` di BeautifulSoup
    # restituisce il testo SENZA i delimitatori `<!-- -->`, quindi ricomponendo
    # il markup con str(child) i commenti diventano TESTO VISIBILE. E' l'origine
    # della "scritta" comparsa nel sito il 2026-07-25: "GSAP library",
    # "ScrollTrigger plugin", "Scripts for the effect" erano i commenti del
    # sorgente Codrops.
    for commento in body.find_all(string=lambda s: isinstance(s, Comment)):
        commento.extract()
    _strip_demo_chrome(body)
    testi_da_riempire = _mark_demo_text(body)

    suffix = "" if slot == 1 else "_2"
    root_id = f"guest-{slot}-{component['id']}"

    css = "\n".join(
        [f"/* --- {p.name} --- */\n{p.read_text(encoding='utf-8', errors='ignore')}"
         for p in paths if p.suffix.lower() == ".css"]
        + ([built_css] if built_css else [])
    )
    # Stadio 1 foto: sostituisce le immagini del componente con anteprime
    # leggere della foto ORIGINALE (muta body per <img>/style inline, riscrive
    # gli url() nel css) e registra il manifest per lo Stadio 2 post-download.
    css, img_var_block = _inline_component_images(body, css, component, slot, root_id)
    markup = "".join(str(child) for child in body.contents).strip()

    js_files = [p for p in paths if p.suffix.lower() == ".js"]
    # Le librerie (.min.js) devono stare a livello globale: se finissero dentro
    # la funzione di mount, il codice della demo non le troverebbe.
    libs = [p for p in js_files if p.name.lower().endswith(".min.js")]
    demo = [p for p in js_files if p not in libs]
    lib_code = "\n".join(
        f"/* --- {p.name} --- */\n{p.read_text(encoding='utf-8', errors='ignore')}"
        for p in libs
    )
    demo_code = "\n".join(
        [f"  /* --- {p.name} --- */\n" + p.read_text(encoding="utf-8", errors="ignore")
         for p in demo]
        + ([f"  /* --- compilato dai sorgenti TS/TSX --- */\n{built_js}"] if built_js else [])
    )

    # Confina il CSS del componente: senza questo il suo `body`/`:root`
    # riscrive sfondo, font e variabili colore di TUTTO il sito.
    css = _scope_component_css(css, root_id)
    hash_lines = ",\n".join(
        f'    "{name}": "{digest}"' for name, digest in sorted(source_hashes.items())
    )
    return (
        f"```html\n"
        f'<section id="{root_id}"\n'
        f'         data-stitch-native-component="{component["id"]}"\n'
        f'         data-motion-component="{component["dom_value"]}"\n'
        f'         data-motion-activation="scroll"\n'
        f'         data-motion-mounted="false">\n'
        f"  <style>\n"
        f"{GUEST_CONTAINMENT_CSS.format(root_id=root_id)}"
        f"{img_var_block}"
        f"{css}\n"
        f"  </style>\n"
        f"{markup}\n"
        f"</section>\n"
        f"<script>\n"
        f'window.__STITCH_SELECTED_COMPONENT{suffix}__ = "{component["id"]}";\n'
        f"window.__STITCH_GUEST{suffix}_SOURCE_SHA256__ = {{\n{hash_lines}\n}};\n"
        f"{lib_code}\n"
        f"function {component['function']}() {{\n"
        f'  const root = document.getElementById("{root_id}");\n'
        f'  if (!root || root.dataset.motionMounted === "true") return;\n'
        f'  root.dataset.motionMounted = "true";\n'
        f"  gsap.from(root, {{\n"
        f'    opacity: 0, duration: 0.9, ease: "power3.out",\n'
        f'    scrollTrigger: {{ trigger: root, start: "top 85%" }}\n'
        f"  }});\n"
        f"{demo_code}\n"
        f"}}\n"
        # Doppio innesco: ScrollTrigger se c'e', altrimenti IntersectionObserver.
        # Cosi' il mount a scroll non dipende dall'ordine di caricamento di GSAP.
        f"(function(){{\n"
        f"  const fire = () => {component['function']}();\n"
        f"  if (window.ScrollTrigger) {{\n"
        f"    ScrollTrigger.create({{\n"
        f'      trigger: "#{root_id}", start: "top 85%",\n'
        f"      once: true, onEnter: fire\n"
        f"    }});\n"
        f"  }} else {{\n"
        f"    new IntersectionObserver((entries, obs) => {{\n"
        f"      entries.forEach((entry) => {{\n"
        f"        if (entry.isIntersecting) {{ fire(); obs.disconnect(); }}\n"
        f"      }});\n"
        f'    }}, {{ rootMargin: "0px 0px -15% 0px" }}\n'
        f'    ).observe(document.getElementById("{root_id}"));\n'
        f"  }}\n"
        f"}})();\n"
        f"</script>\n"
        f"```\n"
    )


def _contratto_struttura(component_source: str, root_id: str) -> str:
    """Estrae dal SORGENTE VERO la struttura che regge lo scroll, e la detta.

    Il 2026-07-27 Stitch ha consegnato un componente perfetto sulla carta (CSS
    completo, 6 scene, Flip.getState, Flip.fit) e completamente inerte: aveva
    inventato un contenitore `.content-wrap` in `position: absolute` attorno
    alle scene. Con tutti i figli fuori dal flusso la <section> collassa a 0px,
    quindi la corsa di scroll e' zero e nessuno ScrollTrigger avanza mai.

    Il sorgente originale non ha nessun contenitore: le scene sono figlie
    DIRETTE, ognuna alta 100vh, impilate nel flusso. Sono loro a creare i
    700vh di corsa su cui il componente lavora. Questa funzione conta le scene
    reali e scrive il contratto con i numeri di QUESTO componente, cosi' la
    regola vale per tutti e 31 senza scriverla a mano per ognuno.
    """
    # Una "scena" non e' qualunque blocco: e' un blocco che nel CSS del
    # sorgente e' alto UNO SCHERMO. Senza questo vincolo il conteggio prende
    # anche le celle di una griglia (onscroll-filter dava 22 "scene", cioe'
    # 2200vh di corsa: una sciocchezza che avrebbe fatto piu' danni della
    # regola mancante).
    classi_a_schermo = set(
        re.findall(
            r"\.([A-Za-z][\w-]*)[^{}]*\{[^{}]*height:\s*100(?:vh|svh|dvh)",
            component_source,
        )
    )
    if not classi_a_schermo:
        return ""
    n = 0
    for classe in classi_a_schermo:
        usi = len(
            re.findall(
                rf'<(?:section|div)\b[^>]*class="[^"]*\b{re.escape(classe)}\b',
                component_source,
            )
        )
        n = max(n, usi)
    if n < 2 or n > 14:
        return ""
    corsa = n * 100
    return (
        f"\n### CONTRATTO DI STRUTTURA — QUESTO E' CIO' CHE FA FUNZIONARE IL COMPONENTE\n\n"
        f"Nel sorgente qui sotto ci sono **{n} scene** impilate. Ognuna e' alta\n"
        f"uno schermo intero e sta NEL FLUSSO normale: sono loro, sommandosi, a\n"
        f"creare i **~{corsa}vh di corsa di scroll** su cui tutta l'animazione\n"
        f"lavora. Senza quella corsa il componente non ha niente da percorrere.\n\n"
        f"Quindi, non negoziabile:\n\n"
        f"1. Le {n} scene sono figlie DIRETTE di `#{root_id}`. Non avvolgerle in\n"
        f"   un contenitore che ti inventi tu.\n"
        f"2. Ogni scena: `position: relative; height: 100vh;`. Nel flusso.\n"
        f"3. `position: absolute` si usa SOLO per i layer che si sovrappongono\n"
        f"   DENTRO una scena (le immagini, i titoli sovrapposti). MAI su una\n"
        f"   scena, MAI su un contenitore di scene.\n"
        f"4. A fine lavoro `#{root_id}` deve risultare alta circa {corsa}vh.\n"
        f"   Se ti viene alta uno schermo o zero, hai messo qualcosa in\n"
        f"   `absolute` che doveva restare nel flusso: e' l'unico errore\n"
        f"   possibile, cercalo li'.\n\n"
        f"COSA E' GIA' SUCCESSO (2026-07-27): Stitch ha avvolto le scene in un\n"
        f"`<div class=\"content-wrap\">` con `position:absolute; height:100%`.\n"
        f"Il genitore era alto 0, quindi il wrapper era alto 0, quindi le {n}\n"
        f"scene si sono sovrapposte tutte nello stesso punto e si sono disegnate\n"
        f"sopra le sezioni successive: i titoli del componente sono finiti\n"
        f"stampati sopra il footer. Il codice era giusto, la struttura no.\n"
    )


def _inventario_animazioni(component_source: str) -> tuple[list[str], int, int]:
    """Elenca le funzioni di animazione del sorgente e conta tween e trigger.

    Il 2026-07-27 e' emerso che il "wow" di questi componenti non sta nel loro
    effetto principale, ma nel fatto che piu' strati di movimento scrubbato
    avvengono INSIEME. one-element-scroll ha sei funzioni: il Flip fra i
    layout, i titoli che entrano da direzioni alternate, le foto secondarie
    che sbocciano da desaturato, il testo che viaggia controcorrente,
    l'elemento che schiarisce, le colonne che si aprono a ventaglio.
    Stitch ne riproduce UNA e considera il lavoro finito, perche' noi gli
    contavamo le scene (il DOM) e mai i comportamenti (il movimento).
    """
    nomi: list[str] = []
    for match in re.finditer(
        r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:\([^)]*\)|[\w$]+)\s*=>\s*\{"
        r"|function\s+([A-Za-z_$][\w$]*)\s*\(",
        component_source,
    ):
        nome = match.group(1) or match.group(2)
        corpo = component_source[match.end(): match.end() + 1400]
        if not re.search(r"\bgsap\s*\.\s*(?:to|from|fromTo|timeline|set)\s*\(", corpo):
            continue
        # Il contorno della pagina demo di Codrops (le card "related demos",
        # la barra .frame, i .credits) lo togliamo sempre: se lo elencassimo
        # qui, Stitch lo ricostruirebbe dentro il sito del cliente.
        if re.search(r"\.card-wrap|\.credits|related|\.frame__|demo", corpo, re.I):
            continue
        if nome not in nomi and nome not in ("init", "preloadImages"):
            nomi.append(nome)
    # Conta OGNI forma di movimento, non solo i tween con nome: molti
    # componenti del catalogo usano classi o timeline invece di funzioni
    # dichiarate, e con un conteggio stretto restavano senza contratto.
    tween = len(
        re.findall(
            r"\bgsap\s*\.\s*(?:to|from|fromTo|timeline|set)\s*\("
            r"|\b(?:tl|timeline|t1)\s*\.\s*(?:to|from|fromTo|add)\s*\(",
            component_source,
        )
    )
    trigger = len(re.findall(r"scrollTrigger\s*:|ScrollTrigger\s*\.\s*create", component_source))
    return nomi, tween, trigger


def _contratto_animazioni(component_source: str) -> str:
    """Detta l'inventario dei comportamenti da riprodurre, coi numeri veri."""
    nomi, tween, trigger = _inventario_animazioni(component_source)
    if tween < 4:
        return ""
    if nomi:
        elenco = (
            f"Le funzioni da riprodurre, tutte:\n\n"
            + "\n".join(f"   - `{n}`" for n in nomi)
            + "\n\n"
        )
        intestazione = (
            f"Il sorgente contiene **{len(nomi)} funzioni di animazione distinte**,\n"
            f"**{tween} movimenti** e **{trigger} agganci allo scroll**."
        )
    else:
        elenco = ""
        intestazione = (
            f"Il sorgente contiene **{tween} movimenti** distinti e\n"
            f"**{trigger} agganci allo scroll**, distribuiti fra metodi e\n"
            f"timeline. Vanno riprodotti tutti."
        )
    return (
        f"\n### CONTRATTO DI MOVIMENTO — IL 'WOW' STA QUI, NON NELL'EFFETTO PRINCIPALE\n\n"
        f"{intestazione} Non sono\n"
        f"alternative fra cui scegliere: girano TUTTE INSIEME, sovrapposte,\n"
        f"ed e' la loro simultaneita' a fare l'effetto cinematografico.\n\n"
        f"{elenco}"
        f"Mentre l'effetto principale avviene, contemporaneamente i titoli si\n"
        f"muovono, le immagini secondarie cambiano scala e filtro, i testi\n"
        f"viaggiano in direzione opposta allo scroll. Togline una e il\n"
        f"componente diventa piatto pur restando 'corretto'.\n\n"
        f"ERRORE GIA' FATTO (2026-07-27): consegnata UNA funzione su sei, con\n"
        f"dentro solo il Flip. Tecnicamente il componente c'era. Sullo schermo\n"
        f"non succedeva quasi niente. Se nel tuo codice finale ci sono meno di\n"
        f"{tween} chiamate `gsap.to/from/fromTo` dentro la sezione Guest, hai\n"
        f"perso degli strati: torna nel sorgente e riprendili.\n\n"
        f"Conserva anche i VALORI: gli ease (`sine`, `sine.inOut`), le distanze\n"
        f"(±150, ±250), i filtri (`brightness(180%) saturate(0%)`), gli scarti\n"
        f"di timeline (`+=0.5`). Sono la taratura che rende il movimento\n"
        f"elegante invece che brusco: cambiarli e' rifare il componente.\n"
    )


def _guest_bundle_text(
    component: dict, component_source: str, slot: int, source_hashes: dict[str, str]
) -> str:
    """Testo del bundle Guest.

    Regola appresa dagli export che funzionavano davvero: in questa fase Stitch
    deve avere UN SOLO compito, incollare i sorgenti 1:1. Ogni lavoro extra
    (cablare il mount, trascrivere gli SHA256, inventare i marker) e' lavoro che
    compete con la copia e che lui sacrifica per primo, fingendo. Quindi qui
    tutto cio' che non e' "incolla" glielo consegniamo GIA' SCRITTO: deve solo
    copiare lo scheletro e riempirne i due buchi.
    """
    other = 2 if slot == 1 else 1
    suffix = "" if slot == 1 else "_2"
    function_name = component["function"]
    root_id = f"guest-{slot}-{component['id']}"
    hash_lines = ",\n".join(
        f'    "{name}": "{digest}"' for name, digest in sorted(source_hashes.items())
    )
    # PERCHE' IL BLOCCO PREMONTATO E' DISATTIVATO (2026-07-26, prova alla mano).
    #
    # L'idea "gli consegno il blocco finito, lui copia" funziona per cose
    # piccole (i 6 tag <script> GSAP: copiati; il motion kit da 2,5 KB:
    # copiato) ma FALLISCE sul Guest: davanti a 44 KB con l'ordine "ricopia
    # carattere per carattere" Stitch non trascrive, RISCRIVE tutto da zero
    # con classi sue e perde ogni token e ogni marker (misurato: Flip.getState
    # 0, data-stitch-native-component 0).
    #
    # L'export che invece FUNZIONAVA (stitch_stitch_reference_transcriber)
    # riceveva i SORGENTI GREZZI da 95 KB e l'ordine "estrai la matematica e
    # il comportamento, poi applicali": ha prodotto una sezione da 16 KB con i
    # token veri (clipPathDirections, tlEnter, tlLeave) e le classi originali
    # (hover-grid-section 57 volte). Cioe': Stitch sa ESTRARRE bene da un
    # sorgente grande, non sa TRASCRIVERLO.
    #
    # Per riattivare il blocco premontato basta rimettere True qui, ma serve
    # una prova che la trascrizione funzioni.
    USA_BLOCCO_PREMONTATO = False
    montato = _assembled_guest_block(component, slot, source_hashes) if USA_BLOCCO_PREMONTATO else None
    if montato:
        # Caso normale (28 componenti su 31): blocco gia' completo. Non gli
        # resta nessun lavoro se non copiare, quindi non ha niente da saltare.
        return (
            f"# VERIFIED ORIGINAL GUEST COMPONENT #{slot} — GIA' MONTATO\n\n"
            f"**QUESTO BLOCCO E' GIA' COMPLETO E FUNZIONANTE. IL TUO UNICO\n"
            f"COMPITO E' COPIARLO NEL SITO ESATTAMENTE COM'E'.\n"
            f"Non devi assemblare niente, non devi cercare altri file, non devi\n"
            f"convertire niente, non devi scrivere una riga di codice tua.\n"
            f"CSS, markup, libreria, mount e SHA256 sono gia' tutti al loro posto.**\n\n"
            f"### ⛔ DIVIETO ASSOLUTO DI ABBREVIARE — ERRORE PIU' FREQUENTE ⛔\n\n"
            f"E' SEVERAMENTE VIETATO scrivere `...` (tre puntini) dentro la\n"
            f"`<section>` al posto del markup. E' vietato anche ogni altro modo di\n"
            f"accorciare: `<!-- ... -->`, `<!-- resto del markup -->`,\n"
            f"`[markup invariato]`, `// come sopra`, `etc.`, o saltare righe.\n\n"
            f"Se scrivi `<section ...> ... </section>` la sezione resta VUOTA:\n"
            f"larghezza 0, altezza 0, zero figli. Il componente NON si vede e il\n"
            f"lavoro e' FALLITO. E' gia' successo: non rifarlo.\n\n"
            f"Il markup dentro la sezione va incollato INTEGRALMENTE, tag per tag,\n"
            f"dal primo all'ultimo carattere. Se il blocco ti sembra lungo,\n"
            f"copialo lo stesso per intero: la lunghezza non e' una scusa.\n\n"
            f"**REGOLE DI INSERIMENTO:\n"
            f"1. Incollalo come NUOVA SEZIONE IN PIU', senza cancellare o sostituire nessuna sezione esistente.\n"
            f"2. NON deve essere l'ultima sezione prima del footer: mettilo penultimo o tra le sezioni intermedie, altrimenti lo scroll si blocca.\n"
            + ("" if SINGLE_GUEST else
               f"3. NON toccare il Guest Component #{other}: i due sono sezioni distinte e devono coesistere.\n")
            + f"3. DENTRO il blocco non cambi niente: niente classi rinominate, niente codice accorciato, niente riscritture.**\n\n"
            f"## RACCORDO VISIVO OBBLIGATORIO (fuori dal blocco, mai dentro)\n\n"
            f"Il componente NON deve sembrare un sito incollato dentro un altro.\n"
            f"Raccordalo cosi', lavorando SOLO sul guscio:\n"
            f"- AGGIUNGI sopra il blocco, dentro la stessa `<section>`, un'intestazione\n"
            f"  con kicker e titolo nella TIPOGRAFIA E PALETTE DEL SITO (stesso font\n"
            f"  serif dei titoli, stessi colori, stesso passo delle altre sezioni),\n"
            f"  con un testo coerente col ristorante (es. 'La Galleria', 'Il Territorio').\n"
            f"- Imposta sul wrapper lo SFONDO in palette del sito, e padding verticale\n"
            f"  identico alle altre sezioni, cosi' non c'e' stacco visivo.\n"
            f"- Il componente deve stare nel flusso: NESSUNA sovrapposizione con le\n"
            f"  sezioni adiacenti, nessun contenuto che sborda sopra o sotto.\n"
            f"- VIETATO invece toccare l'interno del blocco: font, colori, classi e\n"
            f"  animazioni del componente restano ORIGINALI. Se 'adatti' il motore,\n"
            f"  il componente muore: adatta solo il vestito attorno.\n\n"
            f"## UNICA COSA DA CAMBIARE DENTRO IL BLOCCO: I TESTI MARCATI\n\n"
            f"Il componente arriva col copy del suo demo originale, che parla\n"
            f"d'altro (marchi di abbigliamento, testi in inglese, nomi inventati).\n"
            f"Nel sito del cliente sarebbe assurdo.\n\n"
            f"Ogni tag con `data-stitch-fill=\"true\"` contiene un testo-segnaposto:\n"
            f"SOSTITUISCI SOLO IL TESTO di quei tag con contenuti reali presi\n"
            f"dalle reference del cliente (nome cantina/ristorante, nomi dei vini,\n"
            f"del territorio, dei piatti), nella stessa lingua del sito.\n\n"
            f"REGOLE STRETTE su questa sostituzione:\n"
            f"- cambia SOLO il testo dentro il tag; NON toccare il tag, le sue\n"
            f"  classi, i suoi attributi, la sua posizione o il codice attorno;\n"
            f"- mantieni una lunghezza simile all'originale, o il layout si rompe;\n"
            f"- lascia `data-stitch-fill=\"true\"` dov'e';\n"
            f"- NON inventare nomi o fatti che non compaiono nelle reference;\n"
            f"- tutto cio' che NON ha `data-stitch-fill` va copiato letterale.\n\n"
            f"Selected: `{component['name']}` (`{component['id']}`)\n"
            f"Original root: `{component['source_root']}`\n\n"
            f"## BLOCCO DA COPIARE\n\n{montato}\n"
            f"## VERIFICA FINALE — FALLA PRIMA DI RISPONDERE\n\n"
            f"1. Cerca `...` dentro la tua `<section id=\"{root_id}\">`. Se lo\n"
            f"   trovi, hai abbreviato: torna indietro e incolla il markup vero.\n"
            f"2. La sezione deve contenere DECINE di tag reali, non un segnaposto.\n"
            f"3. Nel sito devono comparire letteralmente "
            f"{', '.join(repr(t) for t in component['required_tokens'])}. "
            f"Se manca anche uno solo, non hai copiato tutto il blocco: rifallo.\n"
        )

    return (
        f"# VERIFIED ORIGINAL GUEST COMPONENT #{slot}\n\n"
        f"**IL TUO COMPITO: ESTRARRE IL MOTORE DI QUESTO COMPONENTE E APPLICARLO.**\n\n"
        f"NON devi ricopiare tutti i sorgenti carattere per carattere: sono file\n"
        f"di demo, contengono anche cornice, pagine correlate e librerie che qui\n"
        f"non servono. Se provi a trascriverli tutti finisci per riscrivere il\n"
        f"componente a modo tuo e perdere la sua fisica: e' l'errore piu' grave.\n\n"
        f"Devi invece fare esattamente questo, come un tecnico che riusa un motore:\n"
        f"1. LEGGI i sorgenti allegati qui sotto e capisci COME FUNZIONA il\n"
        f"   componente: la sua matematica, le sue timeline, i suoi trigger.\n"
        f"2. RIPRODUCI la STRUTTURA DOM che gli serve, con le SUE classi originali\n"
        f"   (non rinominarle: gli script le cercano per nome).\n"
        f"3. COPIA LETTERALMENTE il codice JavaScript che contiene la matematica\n"
        f"   e le timeline: quello NON si riscrive e NON si semplifica.\n"
        f"4. SCARTA quello che e' solo cornice della demo: barra dei link Codrops,\n"
        f"   sezione 'More you might like', card di altre demo, librerie vendor\n"
        f"   (gsap.min.js e simili: sono gia' caricate dal CDN nel sito).\n\n"
        f"Il risultato giusto e' una sezione di CIRCA 15-20 KB che contiene TUTTE\n"
        f"le scene del componente con le loro classi originali. Se ti viene una\n"
        f"sezione da 4-5 KB con 3 blocchi generici, hai semplificato il\n"
        f"componente: e' l'errore piu' grave, perche' la spettacolarita' sta\n"
        f"proprio nella sua struttura.\n\n"
        + _contratto_struttura(component_source, root_id)
        # Il contratto di MOVIMENTO non sta qui: viaggia col passaggio
        # separato (STITCH_GUEST_MOTION_PROMPT.txt). In questo messaggio
        # Stitch deve pensare solo alla struttura, altrimenti torna a fare
        # una cosa sola su sei.
        +
        f"\nCONTA LE SCENE nel sorgente `index.html` qui sotto (i blocchi ripetuti\n"
        f"tipo `content--grid`, `content--column`, `content--lines`,\n"
        f"`content--sides`) e RIPRODUCILE TUTTE, con quei nomi di classe. Se una\n"
        f"scena contiene 9 immagini, nel sito ce ne sono 9: riusa le foto del\n"
        f"sito se non ne hai abbastanza, ma non ridurre il numero di nodi o la\n"
        f"matematica del componente si rompe.\n\n"
        f"E' SEVERAMENTE VIETATO sostituire la matematica originale con un\n"
        f"surrogato in GSAP vanilla (`gsap.to({{opacity:1}})` al posto di una\n"
        f"timeline Flip), oppure inventare classi tue tipo `.g1-gallery`,\n"
        f"`.g1-container`: se nel codice finale compaiono classi che non esistono\n"
        f"nei sorgenti qui sotto, hai riscritto il componente e hai FALLITO.\n\n"
        f"**LA SEZIONE DEVE AVERE UN'ALTEZZA VERA. E' L'ERRORE CHE HA RESO\n"
        f"INERTE IL COMPONENTE IL 2026-07-27.**\n"
        f"Il codice era giusto: CSS completo, 6 scene, `Flip.getState`,\n"
        f"`Flip.fit`. Ma il wrapper delle scene era `position: absolute` e, da\n"
        f"53em in su, anche `.frame` diventava `absolute`. Con TUTTI i figli\n"
        f"fuori dal flusso, la `<section>` collassava a **0 pixel di altezza**\n"
        f"(misurato in browser). Zero altezza = zero scroll = nessuno\n"
        f"ScrollTrigger avanza mai: il componente esiste nel codice e non\n"
        f"succede niente sullo schermo.\n"
        f"Regole che ne derivano, non negoziabili:\n"
        f"- almeno UN figlio diretto della section deve stare nel flusso\n"
        f"  normale (`position: static` o `relative`) e dare l'altezza;\n"
        f"- le scene che si susseguono nello scroll stanno IMPILATE nel\n"
        f"  flusso, una sotto l'altra, ognuna alta ~100vh: e' quello che crea\n"
        f"  la corsa di scroll su cui il componente lavora;\n"
        f"- `position: absolute` si usa per gli elementi che si SOVRAPPONGONO\n"
        f"  dentro una scena, mai per il contenitore che regge le scene;\n"
        f"- se il sorgente originale usa `position: fixed` o `sticky` per\n"
        f"  l'elemento che viaggia, conservalo: quello e' corretto, e' il\n"
        f"  CONTENITORE che non deve mai uscire dal flusso;\n"
        f"- prima di consegnare, verifica che la section sia alta almeno\n"
        f"  quanto la somma delle sue scene. Se e' alta 0, non hai finito.\n\n"
        f"**REGOLA D'ORO ZERO-DISTRUZIONE & SCROLL-SAFE:\n"
        f"1. QUESTO COMPONENTE VA AGGIUNTO COME UNA NUOVA SEZIONE IN PIÙ (`<section>`) ALL'INTERNO DEL SITO!\n"
        f"2. È SEVERAMENTE VIETATO CANCELLARE O SOSTITUIRE LE SEZIONI ESISTENTI (es. 'I Nostri Vini', 'Bistrot', 'L'Azienda', 'Degustazioni', ecc.) PER FARGLI POSTO!\n"
        f"3. NON POSIZIONARE MAI QUESTO COMPONENTE COME ULTIMA SEZIONE PRIMA DEL FOOTER! Posizionalo come PENULTIMA o tra le sezioni intermedie, in modo che ci sia sempre almeno un'altra sezione dopo di lui prima del footer, altrimenti lo scroll si blocca!\n"
        + ("" if SINGLE_GUEST else
           f"4. NON TOCCARE, NON SOSTITUIRE E NON FONDERE IL GUEST COMPONENT #{other}: i due Guest sono SEZIONI DISTINTE e devono coesistere entrambi nel sito finale.\n")
        + f"**\n\n"
        f"Selected: `{component['name']}` (`{component['id']}`)\n"
        f"Original root: `{component['source_root']}`\n\n"
        f"## L'INVOLUCRO DELLA SEZIONE — QUESTO SI COPIA ESATTO (e' corto)\n\n"
        f"Questo guscio e' l'unica parte da riprodurre alla lettera: sono poche\n"
        f"righe e contengono i marker che il controllo automatico verifica.\n"
        f"Dentro ci metti la struttura e il codice che hai ESTRATTO dai sorgenti.\n\n"
        f"```html\n"
        f'<section id="{root_id}"\n'
        f'         data-stitch-native-component="{component["id"]}"\n'
        f'         data-motion-component="{component["dom_value"]}"\n'
        f'         data-motion-activation="scroll"\n'
        f'         data-motion-mounted="false">\n'
        f"  <style>\n"
        f"{GUEST_CONTAINMENT_CSS.format(root_id=root_id)}"
        f"  /* Qui va il CSS del componente che ti serve davvero, con le sue\n"
        f"     classi originali. Prendilo dai file ORIGINAL FILE qui sotto e\n"
        f"     scarta le regole della cornice demo (.frame, .credits, .outro,\n"
        f"     .card-wrap) e i reset globali su body/html. La gabbia qui sopra\n"
        f"     tiene il componente dentro la sezione anche con position:fixed. */\n"
        f"  </style>\n"
        f"  <!-- Qui va la struttura DOM del componente, con le SUE classi\n"
        f"       originali prese da index.html. Riproducila fedelmente: gli\n"
        f"       script la cercano per nome di classe. Salta la cornice demo. -->\n"
        f"</section>\n"
        f"<script>\n"
        f'window.__STITCH_SELECTED_COMPONENT{suffix}__ = "{component["id"]}";\n'
        f"window.__STITCH_GUEST{suffix}_SOURCE_SHA256__ = {{\n{hash_lines}\n}};\n"
        f"function {function_name}() {{\n"
        f'  const root = document.getElementById("{root_id}");\n'
        f'  if (!root || root.dataset.motionMounted === "true") return;\n'
        f'  root.dataset.motionMounted = "true";\n'
        f"  gsap.from(root, {{\n"
        f"    opacity: 0, duration: 0.9, ease: \"power3.out\",\n"
        f'    scrollTrigger: {{ trigger: root, start: "top 85%" }}\n'
        f"  }});\n"
        f"  /* Qui va il JavaScript del componente: la sua matematica e le sue\n"
        f"     timeline, COPIATE LETTERALMENTE dai file ORIGINAL FILE qui sotto.\n"
        f"     Questa parte non si riscrive e non si semplifica: e' il motore.\n"
        f"     Cambia solo i selettori globali in ricerche dentro `root`\n"
        f"     (document.querySelector -> root.querySelector), cosi' il\n"
        f"     componente non tocca il resto del sito.\n"
        f"     Scarta invece il codice della cornice demo (es. la funzione che\n"
        f"     anima le card 'More you might like'). */\n"
        f"}}\n"
        # Doppio innesco: ScrollTrigger se c'e', altrimenti IntersectionObserver.
        # Cosi' il mount a scroll non dipende dall'ordine di caricamento di GSAP.
        f"(function(){{\n"
        f"  const fire = () => {function_name}();\n"
        f"  if (window.ScrollTrigger) {{\n"
        f"    ScrollTrigger.create({{\n"
        f'      trigger: "#{root_id}", start: "top 85%",\n'
        f"      once: true, onEnter: fire\n"
        f"    }});\n"
        f"  }} else {{\n"
        f"    new IntersectionObserver((entries, obs) => {{\n"
        f"      entries.forEach((entry) => {{\n"
        f"        if (entry.isIntersecting) {{ fire(); obs.disconnect(); }}\n"
        f"      }});\n"
        f'    }}, {{ rootMargin: "0px 0px -15% 0px" }}\n'
        f'    ).observe(document.getElementById("{root_id}"));\n'
        f"  }}\n"
        f"}})();\n"
        f"</script>\n"
        f"```\n\n"
        f"## CONTROLLO DI ONESTA' (fallo tu prima di rispondere)\n\n"
        f"Gli SHA256 nell'involucro sono gia' quelli veri: NON riscriverli, NON\n"
        f"inventarne altri, NON sostituirli con segnaposto tipo `\"hash2\"`.\n\n"
        f"LA PROVA CHE HAI USATO IL MOTORE VERO E NON UN SURROGATO:\n"
        f"nel codice finale devono comparire LETTERALMENTE queste stringhe, che\n"
        f"vengono dai sorgenti qui sotto:\n"
        + "".join(f"  - {token!r}\n" for token in component["required_tokens"])
        + f"\nSe anche una sola manca, hai riscritto il componente con roba tua:\n"
        f"torna ai sorgenti, ritrova quella parte di codice e copiala letterale.\n"
        f"Devono comparire anche le CLASSI ORIGINALI del componente (quelle che\n"
        f"leggi nel suo index.html), non classi inventate da te.\n\n"
        f"{component_source}\n"
    )


# ---------------------------------------------------------------------------
# IDENTITA' INVENTATA DEL SITO
#
# Le 2 reference di un batch sono DUE AZIENDE DIVERSE (verificato: Ca' San
# Sebastiano + Mauro Sebaste). Chiedendo "3 sezioni da A + 3 da B" usciva un
# sito che pubblicizzava due cantine insieme, con due indirizzi e due telefoni.
# Decisione 2026-07-26: il sito e' di una cantina INVENTATA che eredita
# l'estetica di entrambe.
#
# Il nome NON lo inventa Stitch: "inventa" e' la porta da cui rientra il
# template IA ("Welcome to our winery"). Lo genera Python e glielo consegna
# come dato, coerente e gia' scritto. Effetto collaterale utile: cambia a ogni
# batch, quindi contribuisce alla varieta' su scala.
# ---------------------------------------------------------------------------

_BRAND_PREFIXES = (
    "Tenuta", "Cascina", "Podere", "Cantine", "Villa", "Corte", "Borgo", "Vigna",
)
_BRAND_NAMES = (
    "Valdarena", "Montelvino", "Ca' Bruciata", "San Faustino", "Roncalto",
    "Bricco Sereno", "Costalunga", "Fontanabuona", "Terre Alte", "Vallescura",
    "Sant'Ilario", "Pian del Gelso", "Colle Rosso", "Ca' Vecchia", "Montebello",
    "Rocca Grimalda", "Prato Sole", "Valmarena", "Serralunga Alta", "Ca' Doria",
)
_BRAND_TAGLINES = (
    "Il vino come tempo", "Radici e paesaggio", "Una terra, una famiglia",
    "Il vino come progetto", "Dove nasce il Nebbiolo", "Vigne di collina",
    "Il gesto e la vigna", "Custodi di un territorio",
)
_BRAND_TOWNS = (
    ("Alba", "CN"), ("Barolo", "CN"), ("Camino", "AL"), ("Neive", "CN"),
    ("Canelli", "AT"), ("Nizza Monferrato", "AT"), ("La Morra", "CN"),
    ("Serralunga d'Alba", "CN"), ("Castagnole", "AT"), ("Ovada", "AL"),
)
_BRAND_STREETS = (
    "Via delle Vigne", "Strada della Collina", "Via San Rocco", "Regione Bricco",
    "Via Castello", "Strada Provinciale", "Via Roma", "Localita' Bussia",
)


def _reference_groups(reference_paths: list[Path]) -> dict[str, list[Path]]:
    """Raggruppa le 6 immagini nei 2 siti di origine (`nome__part_01_of_3.jpg`)."""
    gruppi: dict[str, list[Path]] = {}
    for path in reference_paths:
        gruppi.setdefault(re.split(r"__part", path.stem, maxsplit=1)[0], []).append(path)
    return gruppi


def _dominant_colors(paths: list[Path], quanti: int = 8) -> list[tuple]:
    """Colori dominanti di un gruppo di screenshot: (rgb, quota, L, S, H)."""
    import colorsys
    from collections import Counter

    from PIL import Image

    conteggio: Counter = Counter()
    for path in paths:
        try:
            with Image.open(path) as immagine:
                immagine = immagine.convert("RGB")
                immagine.thumbnail((200, 200))
                ridotta = immagine.quantize(colors=24, method=Image.MEDIANCUT).convert("RGB")
                for numero, colore in ridotta.getcolors(200 * 200) or []:
                    conteggio[colore] += numero
        except Exception:
            continue
    totale = sum(conteggio.values()) or 1
    risultato: list[tuple] = []
    for colore, numero in conteggio.most_common(60):
        r, g, b = (canale / 255 for canale in colore)
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        # Scarta i quasi-doppioni: stessa luminosita' e stessa tinta.
        if any(abs(l - altro[2]) < 0.06 and abs(h - altro[4]) < 0.05 for altro in risultato):
            continue
        risultato.append((colore, numero / totale, l, s, h))
        if len(risultato) >= quanti:
            break
    return risultato


def merged_palette(reference_paths: list[Path]) -> dict:
    """UN SOLO sistema di colore, estratto dai pixel veri di ENTRAMBE le reference.

    Il Frankenstein nasce quando si prendono blocchi interi da una reference o
    dall'altra. Qui invece ogni colore riceve un RUOLO che vale su tutto il
    sito, e i ruoli attingono a tutte e due: cosi' entrambe si vedono ovunque e
    niente sembra messo a caso. La scelta non e' lasciata a Stitch: gli
    arrivano gli hex gia' decisi.
    """
    def esadecimale(colore) -> str:
        return "#%02x%02x%02x" % colore

    gruppi = _reference_groups(reference_paths)
    etichette = ["A", "B", "C", "D"]
    per_gruppo = []
    for etichetta, (_nome, percorsi) in zip(etichette, sorted(gruppi.items())):
        per_gruppo.append((etichetta, _dominant_colors(percorsi)))

    tutti = [(etichetta,) + voce for etichetta, colori in per_gruppo for voce in colori]
    if not tutti:
        return {}

    def scegli(predicato, chiave, default=None):
        candidati = [voce for voce in tutti if predicato(voce)]
        if not candidati:
            return default
        return max(candidati, key=chiave)

    # bg: la chiara piu' presente (e' il fondo su cui vive tutto il sito).
    bg = scegli(lambda v: v[3] > 0.82, lambda v: v[2])
    # surface: chiara ma distinta dal bg — e' il riquadro della firma.
    surface = scegli(
        lambda v: v[3] > 0.78 and (bg is None or esadecimale(v[1]) != esadecimale(bg[1])),
        lambda v: v[2],
    )
    # ink: la piu' scura poco satura = testo.
    ink = scegli(lambda v: v[3] < 0.3 and v[4] < 0.35, lambda v: -v[3])
    # accent: il PONTE fra le due reference (oro/ambra). Un accento e' RARO e a
    # meta' scala: se si pesasse per diffusione vincerebbe sempre lo sfondo.
    accent = scegli(
        lambda v: v[4] > 0.35 and 0.03 < v[5] < 0.19 and 0.25 < v[3] < 0.80,
        lambda v: v[4],
    )
    # dark: fascia di stacco (la cantina calda di A). Non il nero puro: serve
    # che si veda che e' bruna, quindi si pesca la piu' satura sopra il nero.
    dark = scegli(lambda v: 0.08 < v[3] < 0.35, lambda v: v[4])

    def voce(scelta) -> dict | None:
        if not scelta:
            return None
        return {"hex": esadecimale(scelta[1]), "from": scelta[0]}

    palette = {
        "bg": voce(bg), "surface": voce(surface), "ink": voce(ink),
        "accent": voce(accent), "dark": voce(dark),
    }
    return {ruolo: dato for ruolo, dato in palette.items() if dato}


def _invented_brand(fingerprint: str) -> dict:
    """Identita' completa e coerente della cantina inventata, dal fingerprint.

    Deterministica: lo stesso batch produce sempre lo stesso brand, cosi' un
    rilancio non cambia il sito a meta' strada.
    """
    def pick(sequence, offset: int):
        return sequence[int(fingerprint[offset:offset + 8], 16) % len(sequence)]

    prefix = pick(_BRAND_PREFIXES, 32)
    core = pick(_BRAND_NAMES, 40)
    town, provincia = pick(_BRAND_TOWNS, 48)
    street = pick(_BRAND_STREETS, 56)
    civico = int(fingerprint[8:12], 16) % 80 + 1
    telefono = (
        f"+39 0{int(fingerprint[12:15], 16) % 900 + 100} "
        f"{int(fingerprint[15:19], 16) % 900000 + 100000}"
    )
    nome = f"{prefix} {core}"
    slug = re.sub(r"[^a-z0-9]+", "", nome.lower())
    return {
        "name": nome,
        "tagline": pick(_BRAND_TAGLINES, 24),
        "town": town,
        "province": provincia,
        "address": f"{street} {civico}, {town} ({provincia})",
        "phone": telefono,
        "email": f"info@{slug}.it",
    }


_PALETTE_ROLES = {
    "bg": "fondo di TUTTE le sezioni chiare",
    "surface": "il riquadro chiaro della FIRMA sovrapposto alle foto",
    "ink": "tutti i testi",
    "accent": "oro: kicker, filetti, bordi dei bottoni, numeri",
    "dark": "fasce di stacco a fondo scuro (1 o 2 sezioni, non di piu')",
}


def build_identity_block(brand: dict, forbidden: list[str], palette: dict | None = None) -> str:
    """Blocco da appendere al prompt di fase 1: l'identita' consegnata gia' fatta."""
    vietati = "\n".join(f"- {nome}" for nome in forbidden) or "- (nessuno rilevato)"
    colore = ""
    if palette:
        righe = "\n".join(
            f"- `{ruolo}` = **{dato['hex']}** — {_PALETTE_ROLES.get(ruolo, '')} "
            f"(preso dalla Reference {dato['from']})"
            for ruolo, dato in palette.items()
        )
        colore = f"""

## SISTEMA DI COLORE — GIA' ESTRATTO DAI PIXEL DELLE TUE REFERENCE

Non sceglierli tu e non "armonizzarli": sono gia' i colori veri delle due
reference, fusi in un sistema solo. Usa ESATTAMENTE questi valori:

{righe}

Ogni colore ha UN RUOLO che vale su TUTTE le sezioni. Non assegnare un colore
a una sezione perche' "viene da quella reference": e' cosi' che nasce il
Frankenstein. Il fondo e' sempre lo stesso, i titoli sono sempre dello stesso
colore, l'oro fa sempre lo stesso mestiere, dalla prima all'ultima sezione.

COME SCRIVERLI NEL CODICE — ERRORE GIA' SUCCESSO, LEGGILO:

Se usi Tailwind, scrivi SEMPRE il colore col valore arbitrario tra parentesi
quadre e il cancelletto:

    CORRETTO:   bg-[#cda722]   text-[#131313]   border-[#cda722]
    SBAGLIATO:  bg-cda722      text-131313      border-cda722

`bg-cda722` senza `#` e senza parentesi NON e' una classe Tailwind valida: non
colora niente e l'elemento resta trasparente o col colore di default. Nel sito
del 2026-07-26 `bg-f7f3ea` e `text-38170b` non facevano nulla, e alcune aree
erano vuote per questo. Se preferisci, dichiara i colori nella
`tailwind.config` e usa quei nomi — ma allora devi dichiararli TUTTI, non uno
solo, altrimenti succede esattamente quel bug.

QUANTO COLORE USARE — non basta averli, vanno usati con forza:

- `accent` NON e' solo per i testini. Deve comparire almeno DUE volte come
  MASSA piena: una fascia larga che attraversa la sezione, un blocco pieno
  dietro o accanto a una foto, una banda che regge un lato del contenuto.
  Se nel sito finale l'accento esiste solo dentro kicker da 12px, il sito
  risultera' slavato e il lavoro e' sbagliato.
- `dark` serve per ALMENO UNA sezione intera a fondo scuro (contatti,
  riconoscimenti o simile), non solo per un bordo.
- `ink` e' il colore dei titoli: pieno, non una sua versione grigia
  schiarita. I titoli sbiaditi sono l'errore piu' comune.
- Il contrasto tra testo e fondo deve restare alto e leggibile ovunque: i
  riquadri chiari sopra le foto sono coprenti, non velature trasparenti.
"""
    return colore + f"""

## IDENTITA' DEL SITO — DATO GIA' DECISO, NON SI DISCUTE

Le due reference sono DUE AZIENDE DIVERSE. Il sito che costruisci NON e' di
nessuna delle due: e' di UNA SOLA cantina, quella qui sotto. Usa questi dati
identici ovunque servano (hero, navigazione, contatti, footer):

- Nome: **{brand['name']}**
- Tagline: **{brand['tagline']}**
- Indirizzo: **{brand['address']}**
- Telefono: **{brand['phone']}**
- Email: **{brand['email']}**

UN SOLO NOME IN TUTTA LA PAGINA. Un solo indirizzo, un solo telefono.
Se nel sito compaiono due marchi o due indirizzi diversi, hai fallito.

E' VIETATO far comparire i marchi reali delle reference, i loro indirizzi,
telefoni, email o loghi. Nomi vietati rilevati dai file:
{vietati}

QUELLA LISTA NON E' COMPLETA — e' ricavata solo dai nomi dei file. Dentro le
immagini ci sono ALTRI nomi propri reali (il nome del fondatore, della
famiglia, della tenuta, di una linea di vini, di una localita' usata come
marchio). Valgono esattamente come quelli in lista.

REGOLA GENERALE, PIU' FORTE DELLA LISTA: qualunque nome proprio che leggi
nelle reference e che identifica l'azienda, il suo fondatore o la sua
famiglia, NON puo' comparire nel sito. Va sostituito con "{brand['name']}" o,
se e' il nome di una persona, tolto e basta.

Se stai per scrivere un titolo di sezione che e' un nome proprio letto nelle
reference (es. il nome di un produttore o di una cantina storica), FERMATI:
quello e' il caso tipico in cui il marchio reale rientra dalla finestra.
Sostituiscilo con il nome del sito o con l'argomento della sezione
("Le Cantine", "La Famiglia", "Il Fondatore").

IL NOME E I RECAPITI SONO L'UNICA COSA INVENTATA DI QUESTO SITO.

Tutto il resto si TRASCRIVE dalle reference: titoli, kicker, paragrafi (tutti,
non solo il primo), testi dei bottoni, etichette, orari, griglie, dettagli.
Dove una frase nomina l'azienda vera, cambi SOLO quel nome in
"{brand['name']}" e lasci intatto il resto della frase.

VIETATO riscrivere i contenuti con parole tue da brochure ("il racconto di una
passione antica", "un viaggio sensoriale tra i profumi", "l'eccellenza del
territorio", "Discover our wines"). Se una frase non l'hai letta nelle
reference, non va nel sito.
"""


# Parole che non identificano un marchio: compaiono nel titolo di meta' dei
# siti di cantina e da sole non vanno mai vietate.
_GENERIC_BRAND_WORDS = re.compile(
    r"(?i)^(cantina|cantine|azienda|agricola|vini|vino|wine|winery|tenuta|"
    r"societa|srl|ss|home|sito|ufficiale)$"
)


def brands_to_avoid(reference_paths: list[Path]) -> list[str]:
    """Marchi reali da tenere fuori dall'output, dedotti dai nomi file del batch.

    I file arrivano come `Cantina - Ca_ San Sebastiano__part_01_of_3.jpg` o
    `Cantina Mauro Sebaste _ Una storia d_amore per il vino.__part_01_of_3.jpg`:
    il titolo della pagina, con i caratteri illegali sostituiti da `_`.

    Il marchio non sta sempre nello stesso pezzo: in un caso e' dopo il
    trattino, nell'altro e' prima del separatore e attaccato a "Cantina".
    Regola che copre entrambi: si preferisce il segmento che contiene la
    parola generica ("Cantina X" -> "X"); se resta vuoto ("Cantina" da sola)
    si ripiega sul segmento piu' lungo.
    """
    def ripulisci(testo: str) -> str:
        # `Ca_ San Sebastiano` -> `Ca' San Sebastiano`: l'underscore attaccato
        # a una parola era un apostrofo nel titolo originale.
        testo = re.sub(r"(?<=\w)_(?=\s|$)", "'", testo)
        return " ".join(testo.replace("_", " ").split()).strip(" -.,|")

    nomi: list[str] = []
    for path in reference_paths:
        titolo = re.split(r"__part", path.stem, maxsplit=1)[0]
        segmenti = [
            ripulisci(pezzo)
            for pezzo in re.split(r"\s+_\s+|\s+[-–|:]\s+", titolo)
            if ripulisci(pezzo)
        ]
        if not segmenti:
            continue
        scelto = ""
        for segmento in segmenti:
            parole = segmento.split()
            if any(_GENERIC_BRAND_WORDS.match(parola) for parola in parole):
                residuo = " ".join(
                    parola for parola in parole if not _GENERIC_BRAND_WORDS.match(parola)
                ).strip(" -.,")
                if residuo:
                    scelto = residuo
                    break
        if not scelto:
            scelto = max(segmenti, key=len)
        if scelto and scelto.lower() not in {nome.lower() for nome in nomi}:
            nomi.append(scelto)

    # I NOMI DENTRO LE IMMAGINI, NON SOLO QUELLI NEI NOMI FILE — 2026-07-28.
    # Dai nomi file usciva SOLO il marchio principale di ogni reference: due
    # nomi su sei. Il resto - il fondatore, la famiglia, la linea di vini -
    # sta scritto DENTRO gli screenshot, e nessuno lo fermava. Cosi'
    # "PIERINO VELLANO" (una linea di Ca' San Sebastiano) e' diventato il
    # TITOLO di una sezione del sito consegnato, con "Sylla Dogliani" e
    # "La Dama di Langa" nei paragrafi. L'OCR delle reference li legge gia':
    # da qui li aggiungiamo alla lista invece di sperare che Stitch li
    # riconosca da solo. Non deve mai bloccare il giro: se l'OCR non e'
    # disponibile si resta ai nomi dei file, come prima.
    try:
        from read_reference_text import proper_nouns_from_references

        esistenti = {nome.lower() for nome in nomi}
        for nome in proper_nouns_from_references(reference_paths):
            if nome.lower() not in esistenti:
                nomi.append(nome)
                esistenti.add(nome.lower())
    except Exception as exc:
        print(f"  (nomi propri dalle immagini non disponibili: {exc})")

    return nomi


def prepare_identity(reference_paths: list[Path]) -> dict:
    """Solo nome inventato, marchi da evitare e palette. Niente rotazione.

    Serve ai giri corti (solo design): l'identita' e' indispensabile in fase 1
    - senza, Stitch inventa il nome del sito - ma chiamare
    prepare_motion_selection() consumerebbe uno slot di rotazione di
    componente, Framer e regia per un giro che quei pezzi non li usa nemmeno.

    Il nome esce dallo stesso fingerprint del batch, quindi coincide con
    quello che darebbe prepare_motion_selection sulle stesse immagini.
    """
    fingerprint = _batch_fingerprint(reference_paths)
    return {
        "brand": _invented_brand(fingerprint),
        "forbidden_brands": brands_to_avoid(reference_paths),
        "palette": merged_palette(reference_paths),
    }


def prepare_motion_selection(reference_paths: list[Path]) -> dict:
    validate_catalog()
    fingerprint = _batch_fingerprint(reference_paths)
    current = _read_json(SELECTION_PATH, {})
    ledger = _read_json(LEDGER_PATH, {
        "counts": {}, "framer_counts": {}, "style_counts": {}, "history": []
    })

    # La selezione salvata si riusa solo se e' ANCORA ammessa dal pool
    # fine-dining: altrimenti un componente escluso dopo la sua selezione
    # resterebbe cachato per sempre su quel batch.
    component = next((item for item in FINE_DINING_POOL if item["id"] == current.get("component_id")), None) if current.get("batch_fingerprint") == fingerprint else None
    framer = next((item for item in FRAMER_POOL if item["id"] == current.get("framer_id")), None) if current.get("batch_fingerprint") == fingerprint else None
    style = next((item for item in MOTION_STYLE_PROFILES if item["id"] == current.get("style_id")), None) if current.get("batch_fingerprint") == fingerprint else None

    component2 = None
    if not SINGLE_GUEST:
        component2 = next((item for item in FINE_DINING_POOL if item["id"] == current.get("component2_id")), None) if current.get("batch_fingerprint") == fingerprint else None

    if not component or (not SINGLE_GUEST and not component2) or not framer or not style:
        component = _least_used(FINE_DINING_POOL, ledger.setdefault("counts", {}), ledger.get("last_component"), int(fingerprint[:8], 16))
        if not SINGLE_GUEST:
            # Guest #2: pescato dallo stesso catalogo ma SEMPRE diverso dal Guest #1.
            pool2 = tuple(item for item in FINE_DINING_POOL if item["id"] != component["id"])
            component2 = _least_used(pool2, ledger.setdefault("counts", {}), component["id"], int(fingerprint[24:32], 16))
        framer = _least_used(FRAMER_POOL, ledger.setdefault("framer_counts", {}), ledger.get("last_framer"), int(fingerprint[8:16], 16))
        style = _least_used(MOTION_STYLE_PROFILES, ledger.setdefault("style_counts", {}), ledger.get("last_style"), int(fingerprint[16:24], 16))
        scelti = [("counts", component), ("framer_counts", framer), ("style_counts", style)]
        if component2:
            scelti.insert(1, ("counts", component2))
        for key, item in scelti:
            ledger[key][item["id"]] = int(ledger[key].get(item["id"], 0)) + 1
        ledger.update(
            last_component=component["id"],
            last_component2=component2["id"] if component2 else None,
            last_framer=framer["id"], last_style=style["id"],
        )
        ledger.setdefault("history", []).append({
            "batch_fingerprint": fingerprint, "component_id": component["id"],
            "component2_id": component2["id"] if component2 else None,
            "framer_id": framer["id"], "style_id": style["id"],
        })
        LEDGER_PATH.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    component_source, component_hashes = _package_sources(component)
    component2_source, component2_hashes = (
        _package_sources(component2) if component2 else ("", {})
    )
    framer_code, framer_hash = _extract_framer(framer)
    framer_language, framer_source_label, framer_instructions = _framer_bundle_format(
        framer, framer_code
    )
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    # Stadio 1 foto: il manifest viene riempito da _inline_component_images
    # mentre i bundle Guest vengono costruiti. Azzerarlo prima, scriverlo dopo.
    _GUEST_IMAGE_MANIFEST.clear()
    GENERATED_COMPONENT_PATH.write_text(
        _guest_bundle_text(component, component_source, 1, component_hashes),
        encoding="utf-8",
    )
    if component2:
        GENERATED_COMPONENT_2_PATH.write_text(
            _guest_bundle_text(component2, component2_source, 2, component2_hashes),
            encoding="utf-8",
        )
    elif GENERATED_COMPONENT_2_PATH.is_file():
        # Bundle orfano di un giro a due Guest: via, o verrebbe riallegato.
        GENERATED_COMPONENT_2_PATH.unlink()
    # Manifest var-immagine -> foto originale, per lo Stadio 2 post-download.
    GENERATED_IMAGE_MANIFEST_PATH.write_text(
        json.dumps(_GUEST_IMAGE_MANIFEST, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    GENERATED_FRAMER_PATH.write_text(
        f"# VERIFIED ORIGINAL FRAMER INTERACTIVE\n\n"
        f"**REGOLA D'ORO ZERO-DISTRUZIONE: NON CREARE, CANCELLARE, SOSTITUIRE, FONDERE O RIORDINARE SEZIONI. NON TOCCARE IL GUEST COMPONENT GIA INSERITO.**\n\n"
        f"## PALCO DEDICATO — LA FRAMER VA SFRUTTATA, NON NASCOSTA\n\n"
        f"Questa interazione deve essere un MOMENTO del sito, non un dettaglio\n"
        f"schiacciato dentro un'altra sezione. Dalle il suo spazio:\n"
        f"1. Mettila in una sua fascia a larghezza piena, `min-height: 100vh`\n"
        f"   (o l'aspect-ratio del sorgente), centrata. Mai in un angolo.\n"
        f"2. RACCORDO VISIVO (solo attorno, MAI dentro): sopra l'interazione\n"
        f"   aggiungi un kicker e un titolo nella TIPOGRAFIA E PALETTE DEL SITO\n"
        f"   (stesso font serif dei titoli, stessi colori, stesso passo delle\n"
        f"   altre sezioni), con testo coerente col ristorante.\n"
        f"3. Wrapper isolato: `position: relative; overflow: hidden;`. NESSUNA\n"
        f"   sovrapposizione con le sezioni sopra e sotto.\n"
        f"4. L'interno resta ORIGINALE: reagisce a scroll/hover reale come nel\n"
        f"   sorgente. Vietati screenshot, simulazioni GSAP o segnaposto.\n\n"
        f"Selected: `{framer['name']}` (`{framer['id']}`)\n"
        f"Original interaction archive: `{framer['origin']}`\n"
        f"Selected source: `{framer_source_label}`\n"
        f"Source mode: `{framer.get('source_mode', 'portable_react')}`\n"
        f"SHA256: `{framer_hash}`\n\n{framer_instructions}\n\n"
        f"## BLOCCO GIA' MONTATO — COPIALO E BASTA\n\n"
        f"**Questo blocco e' COMPLETO: marker, SHA256, componente React e mount\n"
        f"sono gia' tutti al loro posto. Non devi riempire niente, non devi\n"
        f"convertire niente, non devi scrivere una riga tua. Copialo com'e'.**\n\n"
        f"Il montaggio usa Babel standalone con `type=\"text/babel\"` e\n"
        f"`data-presets=\"react,typescript\"`: e' l'unico modo in cui un\n"
        f"componente TSX gira nel browser senza build. NON sostituirlo con\n"
        f"`<script type=\"module\">`, altrimenti il componente non parte.\n\n"
        f"```html\n"
        f'<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>\n'
        f'<script type="importmap">\n'
        f'{{"imports":{{\n'
        f'  "react": "https://esm.sh/react@18.2.0",\n'
        f'  "react-dom/client": "https://esm.sh/react-dom@18.2.0/client",\n'
        f'  "gsap": "https://esm.sh/gsap@3.12.2",\n'
        f'  "gsap/ScrollTrigger": "https://esm.sh/gsap@3.12.2/ScrollTrigger",\n'
        f'  "@gsap/react": "https://esm.sh/@gsap/react@2.0.2"\n'
        f"}}}}\n"
        f"</script>\n"
        f'<div id="framer-{framer["id"]}"\n'
        f'     data-stitch-framer-interaction="{framer["id"]}"\n'
        f'     data-motion-framer="{framer["dom_value"]}"\n'
        f'     style="position:relative;overflow:hidden;min-height:100vh;"></div>\n'
        f'<script data-presets="react,typescript" data-type="module" type="text/babel">\n'
        f"import {{ createRoot }} from 'react-dom/client';\n"
        f'window.__STITCH_SELECTED_FRAMER__ = "{framer["id"]}";\n'
        f'window.__STITCH_FRAMER_SOURCE_SHA256__ = "{framer_hash}";\n\n'
        f"{framer_code}\n\n"
        f"const framerRoot = document.getElementById("
        f'"framer-{framer["id"]}");\n'
        f"if (framerRoot && !framerRoot.hasChildNodes()) {{\n"
        f"  createRoot(framerRoot).render(<{framer['function']} />);\n"
        f"}}\n"
        f"</script>\n"
        f"```\n\n"
        f"CONTROLLO DI ONESTA': nel sito che consegni devono comparire\n"
        f"letteralmente {', '.join(repr(t) for t in framer['required_tokens'])}. "
        f"Se manca anche uno solo, non hai copiato tutto il blocco: rifallo.\n"
        f"Il render usa `framerRoot` (il div qui sopra) e NON il suo\n"
        f"`parentElement`, altrimenti React cancella i marker della sezione.\n",
        encoding="utf-8",
    )

    result = {
        "batch_fingerprint": fingerprint,
        "manifest_version": "arsenal-v7.1",
        "component_id": component["id"], "component_name": component["name"],
        "function_name": component["function"], "dom_value": component["dom_value"],
        "required_tokens": component["required_tokens"], "authenticity": "portable_original",
        "source_hashes": component_hashes,
        **({
            "component2_id": component2["id"], "component2_name": component2["name"],
            "component2_function_name": component2["function"],
            "component2_dom_value": component2["dom_value"],
            "component2_required_tokens": component2["required_tokens"],
            "component2_source_hashes": component2_hashes,
            "generated_bundle_2": str(GENERATED_COMPONENT_2_PATH),
        } if component2 else {}),
        "framer_id": framer["id"], "framer_name": framer["name"],
        "framer_function_name": framer["function"], "framer_dom_value": framer["dom_value"],
        "framer_required_tokens": framer["required_tokens"], "framer_source_hash": framer_hash,
        "framer_source_mode": framer.get("source_mode", "portable_react"),
        "style_id": style["id"], "style_name": style["name"],
        "generated_bundle": str(GENERATED_COMPONENT_PATH),
        "generated_framer_bundle": str(GENERATED_FRAMER_PATH),
        "guest_image_manifest": str(GENERATED_IMAGE_MANIFEST_PATH),
        # Identita' inventata del sito + marchi reali da tenere fuori: usati dal
        # prompt di fase 1 e dal gate che verifica che non siano trapelati.
        "brand": _invented_brand(fingerprint),
        "forbidden_brands": brands_to_avoid(reference_paths),
        "palette": merged_palette(reference_paths),
        "motion_contract": _motion_contract(
            component, component2, framer, style, component_hashes,
            component2_hashes, framer_hash
        ),
        "final_audit": _final_audit(
            component, component2, framer, style, component_hashes,
            component2_hashes, framer_hash
        ),
    }
    SELECTION_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    import sys
    print(json.dumps(prepare_motion_selection([Path(value) for value in sys.argv[1:]]), indent=2, ensure_ascii=False))
