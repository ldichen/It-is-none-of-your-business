"""
Author: DiChen
Date: 2025-08-07 16:58:39
LastEditors: DiChen
LastEditTime: 2025-08-07 22:10:09
"""

"""
Author: DiChen
Date: 2025-08-01 02:48:00
LastEditors: DiChen
LastEditTime: 2025-08-01 02:59:20
"""

from inoyb import your_turn


@your_turn()
def model_handler(*inputs):
    return [
        "python",
        "model/test_model.py",
        "--data_files",
        inputs[0],
        inputs[1],
        inputs[2],
        "--config_path",
        "model/config.json",
        "--checkpoint",
        "model/Prithvi_EO_V1_100M.pt",
    ]


if __name__ == "__main__":
    model_handler.run()
