from numpy import ma
import argparse


def main(num: int):
    return num * 2


# python test_model.py 指定参数
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test model script")
    parser.add_argument("num", type=int, help="An integer number to double")
    args = parser.parse_args()

    result = main(args.num)
    print(f"Result: {result}")
