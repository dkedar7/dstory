"""dstory — interactive scrollytelling and slide-deck data stories.

Public API:
    Brand, list_presets   — theme/brand handling
    init                  — scaffold a new project
    bundle                — bundle a project into a single HTML file
    vet, Report           — vet a bundled HTML for delivery
    Story, Scene, Meta, Claim, VizzuFrame  — pydantic models for data.json

Optional:
    dstory.prep           — pandas-based data prep helpers (extras: dstory[prep])
"""

from .api import build, BuildResult
from .brand import Brand, list_presets
from .bundle import bundle, BundleResult
from .cookbook import list_recipes, recipe_js, recipe_demo, Recipe
from .scaffold import init, wire_scenes, write_scene, starter_scene_js
from .schema import Story, Meta, Scene, Claim, VizzuFrame, Step, Source, Annotation, SeriesSpec
from .vet import vet, Report, Dimension

__version__ = "0.5.0"

__all__ = [
    "build", "BuildResult",
    "Brand", "list_presets",
    "init", "wire_scenes", "write_scene", "starter_scene_js",
    "list_recipes", "recipe_js", "recipe_demo", "Recipe",
    "bundle", "BundleResult",
    "vet", "Report", "Dimension",
    "Story", "Meta", "Scene", "Claim", "VizzuFrame", "Step", "Source", "Annotation", "SeriesSpec",
    "__version__",
]
