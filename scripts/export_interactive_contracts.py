"""Export reusable v1 schemas and request examples. No service/model access."""
import json
from pathlib import Path
from drama_engine.interactive.models import Creation, Command, BackgroundSpec, Outline
from drama_engine.interactive.generator import StoryOutline, SceneResult


def main():
    root = Path(__file__).resolve().parents[1] / 'docs' / 'contracts' / 'interactive'
    root.mkdir(parents=True, exist_ok=True)
    for model in (Creation, Command, BackgroundSpec, Outline, StoryOutline, SceneResult):
        (root / (model.__name__ + '.schema.json')).write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for form in ('short', 'series'):
        request = Creation(idempotency_key='example-' + form, form=form, character_ids=['replace-with-catalog-character'])
        (root / ('create-' + form + '.json')).write_text(json.dumps(request.model_dump(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
