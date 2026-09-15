# Training the calibrated density head

The deployed bundle in `reader/models/` carries `density.onnx`, a ~522-parameter
head fitted on top of the frozen v8 reader. These two scripts produce it.

## Why it exists

v8's row head is trained with its loss on the **soft-argmax** of `line_logits`,
so only the expectation is supervised; the shape around it never was. Read
directly as a likelihood that softmax is measurably worse than the point
estimate it yields - on the 99 blind hand clicks, 43.7 ml against 29.9 ml. A
filter needs a density, so the shape has to be supervised, which is cheap
because the backbone stays frozen.

## Running them

Both expect the research checkout (`coffee_mesh_pred`) for the frame archive and
the hand-click labels; point `COFFEE_RESEARCH_DIR` at it.

```bash
python -m coffee10.density_data                       # -> _work/density_ds.npz
python -m coffee10.train_density --export _work/onnx_v8_logits/density.onnx
```

`density_data.py` caches the frozen network's three row log-probability curves
and its quality logits for all 257 hand-clicked records. `train_density.py` fits

    out = surf / temperature(aux) + conv_correction(rows)

with the correction initialised at zero, so training starts at exactly the frozen
behaviour and can only be moved by evidence. The target is a Gaussian at the
clicked row whose width is the measured click noise of 3.3 rows. It trains on the
158 non-blind records, picks its epoch count by 5-fold cross-validation inside
that split, and never touches the 99 blind records for any decision.

## Results on the blind split

| | frozen v8 softmax | density head |
|---|---|---|
| negative log-likelihood | 3.577 | 3.450 |
| error of the mode | 43.7 ml | 31.2 ml |
| 90 % interval coverage | 0.919 | 0.899 (nominal 0.90) |
| error, best 20 % by its own sd | 36.9 ml | 24.7 ml |
| error, worst 20 % by its own sd | 57.7 ml | 73.3 ml |

The last two rows are the point: the spread became a reliability signal, which
entropy never was. That is what let the confidence gate be replaced by an
interval.

## One change needed in the research repo

`coffee10/export_onnx.py` must emit the row logits, which the stock exporter
drops:

```python
READER_OUTPUTS = ("h_norm", "y_base", "y_top", "y_surf",
                  "usable_logit", "surface_logit", "entropy", "line_logits")
```

`line_logits` is appended **last** on purpose: the runtime zips this list against
the session outputs, so older bundles whose manifest lacks it keep working.
