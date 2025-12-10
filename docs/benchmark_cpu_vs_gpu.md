# Benchmark Results: CPU vs MPS

I compared the training speed of the CNN model on the MacBook using CPU and MPS (Metal Performance Shaders) backends.

## Methodology

- **Dataset**: 200 images from `datasets/04_batch_100_test` and `datasets/05_batch_100_test_2`.
- **Epochs**: 10
- **Model**: SimpleCNN
- **Batch Size**: 16 (default)

## Results

| Device | Total Time (10 Epochs) | Avg Time per Epoch | Accuracy (End) |
| :--- | :--- | :--- | :--- |
| **CPU** | 4.65s | 0.46s | 87.00% |
| **MPS (GPU)** | **2.68s** | **0.27s** | 95.50% |

## Conclusion

**MPS is approximately 1.7x faster than CPU** for this specific workload. 

Even with a relatively small model and dataset, using the GPU (MPS) provides a significant speedup. The overhead of data transfer deals seems minimal compared to the compute gains.

## Usage

To use specific devices:

```bash
# Auto-detect (prefer MPS)
python3 cnn/train_model.py datasets/04_batch_100_test --device auto

# Force CPU
python3 cnn/train_model.py datasets/04_batch_100_test --device cpu

# Force MPS
python3 cnn/train_model.py datasets/04_batch_100_test --device mps
```
