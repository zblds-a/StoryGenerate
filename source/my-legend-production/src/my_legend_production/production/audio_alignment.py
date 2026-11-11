"""Read-only PCM anchor witness, packaged independently of ignored acceptance scripts."""
import numpy as np
from scipy.signal import correlate, convolve


def match_anchor(reference, decoded, anchor_start, window_samples, sample_rate):
    reference = np.asarray(reference, dtype=np.float64)
    decoded = np.asarray(decoded, dtype=np.float64)
    if (reference.ndim != 1 or decoded.ndim != 1 or sample_rate <= 0 or window_samples < 2
            or anchor_start < 0 or anchor_start + window_samples > len(reference)
            or not np.all(np.isfinite(reference)) or not np.all(np.isfinite(decoded))):
        raise ValueError('INVALID_PCM_ANCHOR')
    window = reference[anchor_start:anchor_start + window_samples]
    window = window - np.mean(window)
    energy = float(np.dot(window, window))
    if energy < 1e-12:
        return {'status': 'silent_reference'}
    if len(decoded) < window_samples:
        return {'status': 'truncated_decoded_audio'}
    low = max(0, anchor_start - 2 * sample_rate)
    high = min(len(decoded), anchor_start + window_samples + 2 * sample_rate)
    search = decoded[low:high]
    if len(search) < window_samples:
        return {'status': 'truncated_decoded_audio'}
    numerator = correlate(search, window, mode='valid', method='fft')
    kernel = np.ones(window_samples)
    sums = convolve(search, kernel, mode='valid', method='fft')
    sums2 = convolve(search * search, kernel, mode='valid', method='fft')
    variance = np.maximum(0, sums2 - sums * sums / window_samples)
    score = np.divide(numerator, np.sqrt(energy * variance), out=np.zeros_like(numerator), where=variance > 1e-12)
    best = int(np.argmax(score))
    confidence = float(np.clip(score[best], -1, 1))
    if confidence < .8:
        return {'status': 'unmatched', 'correlation': confidence}
    offset = int(low + best - anchor_start)
    return {'status': 'matched', 'offset_samples': offset, 'offset_ms': offset * 1000 / sample_rate,
            'correlation': confidence}
