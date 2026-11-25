# What the metrics mean

[Back to the README](../README.md)

This is the output of `audiosteg compare sample sample.stego.wav --details --width 60`, after hiding `Hello`:

```
SNR: 106.2 dB
  How much stronger the sound is than the change. Higher is better. In words: Excellent.
PSNR: 124.1 dB
  How much stronger the loudest possible sound is than the change. Higher is better.
Changed samples: 78 of 188,800 samples (0.04%)
  A sample is one number of one channel. Fewer changes are harder to notice.
Largest change: 1 step (less than 0.01% of the largest possible sample)
  How far one sample moved. One step is the smallest change there is.
Where: from 0.000 s to 0.00345 s
  The time of the first and the last changed sample.
Changed samples in each tenth: 78, 0, 0, 0, 0, 0, 0, 0, 0, 0
  The compared audio, cut into ten equal parts.
Waveform: original
: .    |:.     | .    |:.     |..    |:.     |..    |:.
||||||:|||||:|.||||||:|||||:|.||||||||||||:|.||||||||||||.|.
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
  The loudest sample at each moment, 0.000 s to 4.2812 s.
Waveform: encoded
: .    |:.     | .    |:.     |..    |:.     |..    |:.
||||||:|||||:|.||||||:|||||:|.||||||||||||:|.||||||||||||.|.
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
  The same for the encoded file, at the same scale.
Waveform: difference
|
|
|
|
  The largest change at each moment, enlarged to fill the height.
```

A sample is a whole number where 0 is silence. 8-bit samples are stored from 0 to 255, so 128 is subtracted first. `s` is a sample of the original, `d` is the change of that sample, and all channels count together.

| Metric | Definition | Limits |
| --- | --- | --- |
| SNR | `10 * log10(sum(s^2) / sum(d^2))` dB | An average. A short loud change in a long file can hide in it. There is no SNR if the original is silent. |
| PSNR | `10 * log10(p^2 / mean(d^2))` dB, where `p` is 128, 32768, 8388608, or 2147483648 for 8, 16, 24, or 32 bits | It ignores how loud the audio really is, so quiet audio looks better than it sounds. |
| Changed samples | How many `d` are not 0 | Many tiny changes can be harder to hear than one large change. |
| Largest change | The largest `d` without its sign, also as a percentage of `p`. From one extreme to the other, it is almost 200%. | One step is louder in 8-bit audio than in 16-bit audio. |
| Where | The time of the first changed sample, the end of the last one, and the number of changed samples in each tenth of the audio | A time covers one frame, which is one sample of each channel. |
| Waveform | The largest sample (or change) in each column, without its sign | Very short sounds look as wide as a column. |

The words come from the SNR: Excellent from 70 dB, Good from 50 dB, Fair from 30 dB, and Poor below that or if a silent original changed. Files without any change are Identical. **These limits are this project's choice, not a hearing standard.** They do not consider which sounds cover which others, and no number here can prove what a person hears. If one change passes 1% of the largest possible sample, the summary says that it could be a click. Shown decibels and percentages are rounded down. Shown times have as many digits as `--from` and `--to` need to find the same frame again, up to nine, which is enough for any real audio. If nothing changed, there is no noise and so no SNR and no PSNR.
