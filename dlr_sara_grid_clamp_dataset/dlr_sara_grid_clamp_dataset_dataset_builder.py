import glob
from typing import Any, ClassVar, Iterator, Tuple

import cv2
import numpy as np
import tensorflow_datasets as tfds
import tensorflow_hub as hub


class DlrSaraGridClampDataset(tfds.core.GeneratorBasedBuilder):
    """DatasetBuilder for DLR SARA Pour liquid dataset."""

    VERSION = tfds.core.Version("1.0.0")
    RELEASE_NOTES: ClassVar = {
        "1.0.0": "Initial release.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._embed = hub.load("https://tfhub.dev/google/universal-sentence-encoder-large/5")

    def _info(self) -> tfds.core.DatasetInfo:
        return self.dataset_info_from_configs(
            features=tfds.features.FeaturesDict(
                {
                    "steps": tfds.features.Dataset(
                        {
                            "observation": tfds.features.FeaturesDict(
                                {
                                    "image": tfds.features.Image(
                                        shape=(480, 640, 3),
                                        dtype=np.uint8,
                                        encoding_format="png",
                                        doc="Main camera RGB observation.",
                                    ),
                                    "state": tfds.features.Tensor(
                                        shape=(12,),
                                        dtype=np.float32,
                                        doc="Robot state, consists of [3x robot EEF position, "
                                        "3x robot EEF orientation yaw/pitch/roll calculated "
                                        'with scipy Rotation.as_euler("zxy") Class, 6x robot EEF wrench].',
                                    ),
                                }
                            ),
                            "action": tfds.features.Tensor(
                                shape=(7,),
                                dtype=np.float32,
                                doc="Robot action, consists of [3x robot EEF position, "
                                "3x robot EEF orientation yaw/pitch/roll calculated "
                                'with scipy Rotation.as_euler(="zxy") Class].',
                            ),
                            "discount": tfds.features.Scalar(dtype=np.float32, doc="Discount if provided, default to 1."),
                            "reward": tfds.features.Scalar(
                                dtype=np.float32, doc="Reward if provided, 1 on final step for demos."
                            ),
                            "is_first": tfds.features.Scalar(dtype=np.bool_, doc="True on first step of the episode."),
                            "is_last": tfds.features.Scalar(dtype=np.bool_, doc="True on last step of the episode."),
                            "is_terminal": tfds.features.Scalar(
                                dtype=np.bool_,
                                doc="True on last step of the episode if it is a terminal step, True for demos.",
                            ),
                            "language_instruction": tfds.features.Text(doc="Pour into the mug."),
                            "language_embedding": tfds.features.Tensor(
                                shape=(512,),
                                dtype=np.float32,
                                doc="Kona language embedding. "
                                "See https://tfhub.dev/google/universal-sentence-encoder-large/5",
                            ),
                        }
                    ),
                    "episode_metadata": tfds.features.FeaturesDict(
                        {
                            "file_path": tfds.features.Text(doc="Path to the original data file."),
                        }
                    ),
                }
            )
        )

    def _split_generators(self, dl_manager: tfds.download.DownloadManager):
        """Define data splits."""
        return {
            "train": self._generate_examples(path="data_filtered_filtered/train/episode_*.npy"),
            # 'val': self._generate_examples(path='data/val/episode_*.npy'),
        }

    def _generate_examples(self, path) -> Iterator[Tuple[str, Any]]:
        """Generator of examples for each split."""

        def _parse_example(episode_path):
            # load raw data --> this should change for your dataset
            data = np.load(episode_path, allow_pickle=True)  # this is a list of dicts in our case

            # assemble episode --> here we're assuming demos so we set reward to 1 at the end
            episode = []
            # compute Kona language embedding
            # Same embeddings for all steps
            language_instruction = "Place grid clamp"
            language_embedding = self._embed([language_instruction])[0].numpy()

            for i, step in enumerate(data):
                # Filter out small overshoots in action

                episode.append(
                    {
                        "observation": {
                            "image": cv2.cvtColor(step["image"], cv2.COLOR_BGR2RGB),
                            # 'wrist_image': step['wrist_image'],
                            "state": step["state"],
                        },
                        "action": step["action"].astype(np.float32),
                        "discount": 1.0,
                        "reward": np.float32(step["is_terminal"]),
                        "is_first": i == 0,
                        "is_last": i == (len(data) - 1),
                        "is_terminal": step["is_terminal"],
                        "language_instruction": language_instruction,
                        "language_embedding": language_embedding,
                    }
                )

            # create output data sample
            sample = {"steps": episode, "episode_metadata": {"file_path": episode_path}}

            # if you want to skip an example for whatever reason, simply return None
            return episode_path, sample

        # create list of all examples
        episode_paths = glob.glob(path)

        # for smallish datasets, use single-thread parsing
        for sample in episode_paths:
            yield _parse_example(sample)

        # for large datasets use beam to parallelize data parsing (this will have initialization overhead)
        # beam = tfds.core.lazy_imports.apache_beam
        # return (
        #         beam.Create(episode_paths)
        #         | beam.Map(_parse_example)
        # )
