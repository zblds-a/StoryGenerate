"""Create a credential-free config for network-denied native audio regression tests only."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    value = json.loads((root/'source/my-legend-workflow-dependencies/audio/pipeline/config.example.json').read_text(encoding='utf-8'))
    value['test_only'] = 'network-denied tests replace provider generate methods; not a real audio configuration'
    value['tts'].update(adapter='qianwen_audio_tts', model='qwen-audio-3.1-tts-flash', controls=['instructions'])
    value['sfx'].update(adapter='qianwen_sfx', model='qwen-audio-3.1-tts-next')
    target = args.runtime.resolve()/'dependencies/audio/pipeline/config.live.deepseek-qwen-audio-3.1.json'
    if target.exists():
        raise FileExistsError('Existing audio config preserved')
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Created credential-free fixture config. It is not a real TTS/SFX acceptance result.')


if __name__ == '__main__':
    main()
