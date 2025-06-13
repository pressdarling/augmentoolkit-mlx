"""Sanity check for MLX environment (Metal, tokens/sec)"""
import mlx.core as mx

def main():
    try:
        x = mx.array([1, 2, 3])
        print("MLX array OK:", x)
        print("Apple Metal backend initialised. All good.")
    except Exception as e:
        print("MLX/Metal check failed:", e)

if __name__ == "__main__":
    main()
