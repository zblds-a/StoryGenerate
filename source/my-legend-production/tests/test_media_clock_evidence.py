"""Independent witness must catch delayed, missing and silent audio, not bless metadata."""
import pytest

np=pytest.importorskip('numpy')
pytest.importorskip('scipy')
from my_legend_production.production import audio_alignment as audit


@pytest.mark.parametrize('delay',[-1200,-320,0,320,1200])
def test_finds_actual_signed_offset_despite_gain_change(delay):
    rate=8000
    reference=np.random.default_rng(29).normal(0,.1,rate*4)
    decoded=np.pad(reference,(max(0,delay),0))[max(0,-delay):]*.6
    result=audit.match_anchor(reference,decoded,rate,4000,rate)
    assert result['status']=='matched'
    assert result['offset_samples']==delay
    assert (abs(result['offset_ms'])<=100)==(abs(delay)<=800)


def test_silence_unrelated_and_truncated_audio_cannot_pass():
    rng=np.random.default_rng(61)
    signal=rng.normal(0,.1,16000)
    assert audit.match_anchor(np.zeros(16000),signal,4000,4000,8000)['status']=='silent_reference'
    assert audit.match_anchor(signal,rng.normal(0,.1,16000),4000,4000,8000)['status']=='unmatched'
    assert audit.match_anchor(signal,signal[:1000],8000,4000,8000)['status']=='truncated_decoded_audio'


def test_separate_late_anchor_detects_accumulated_delay():
    rng=np.random.default_rng(47)
    signal=rng.normal(0,.1,48000)
    decoded=np.concatenate([signal[:24000],np.zeros(1600),signal[24000:]])
    early=audit.match_anchor(signal,decoded,8000,4000,8000)
    late=audit.match_anchor(signal,decoded,32000,4000,8000)
    assert early['offset_ms']==0 and late['offset_ms']==200
