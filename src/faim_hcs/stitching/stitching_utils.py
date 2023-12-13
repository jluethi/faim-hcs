from copy import copy

import numpy as np
from numpy._typing import NDArray
from scipy.ndimage import distance_transform_edt
from skimage.transform import EuclideanTransform, warp
from threadpoolctl import threadpool_limits

from faim_hcs.stitching.Tile import Tile, TilePosition


def fuse_linear(warped_tiles: NDArray, warped_masks: NDArray) -> NDArray:
    """
    Fuse transformed tiles using a linear gradient to compute the weighted
    average where tiles are overlapping.

    Parameters
    ----------
    warped_tiles :
        Tile images transformed to the final image space.
    warped_masks :
        Masks indicating foreground pixels for the transformed tiles.

    Returns
    -------
    Fused image.
    """
    dtype = warped_tiles.dtype
    if warped_tiles.shape[0] > 1:
        weights = np.zeros_like(warped_masks, dtype=np.float32)
        for i, mask in enumerate(warped_masks):
            weights[i] = distance_transform_edt(
                warped_masks[i].astype(np.float32),
            )

        denominator = weights.sum(axis=0)
        weights = np.true_divide(weights, denominator, where=denominator > 0)
        weights = np.nan_to_num(weights, nan=0, posinf=1, neginf=0)
        weights = np.clip(
            weights,
            0,
            1,
        )
    else:
        weights = warped_masks

    return np.sum(warped_tiles * weights, axis=0).astype(dtype)


def fuse_mean(warped_tiles: NDArray, warped_masks: NDArray) -> NDArray:
    """
    Fuse transformed tiles and compute the mean of the overlapping pixels.

    Parameters
    ----------
    warped_tiles :
        Tile images transformed to the final image space.
    warped_masks :
        Masks indicating foreground pixels for the transformed tiles.

    Returns
    -------
    Fused image.
    """
    denominator = warped_masks.sum(axis=0)
    weights = np.true_divide(warped_masks, denominator, where=denominator > 0)
    weights = np.clip(
        np.nan_to_num(weights, nan=0, posinf=1, neginf=0),
        0,
        1,
    )

    fused_image = np.sum(warped_tiles * weights, axis=0)
    return fused_image.astype(warped_tiles.dtype)


def fuse_sum(warped_tiles: NDArray, warped_masks: NDArray) -> NDArray:
    """
    Fuse transformed tiles and compute the sum of the overlapping pixels.

    Parameters
    ----------
    warped_tiles :
        Tile images transformed to the final image space.
    warped_masks :
        Masks indicating foreground pixels for the transformed tiles.

    Returns
    -------
    Fused image.
    """
    fused_image = np.sum(warped_tiles, axis=0)
    return fused_image.astype(warped_tiles.dtype)


@threadpool_limits.wrap(limits=1, user_api="blas")
def translate_tiles_2d(block_info, yx_chunk_shape, dtype, tiles):
    """
    Translate tiles to their relative position inside the given block.

    Parameters
    ----------
    block_info :
        da.map_blocks block_info.
    yx_chunk_shape :
        shape of the chunk in yx.
    dtype :
        dtype of the tiles.
    tiles :
        list of tiles.

    Returns
    -------
        translated tiles, translated masks
    """
    array_location = block_info[None]["array-location"]
    chunk_yx_origin = np.array([array_location[3][0], array_location[4][0]])
    warped_tiles = []
    warped_masks = []
    for tile in tiles:
        tile_origin = np.array(tile.get_yx_position())
        transform = EuclideanTransform(
            translation=(chunk_yx_origin - tile_origin)[::-1]
        )
        tile_data = tile.load_data()
        mask = np.ones_like(tile_data)
        warped = warp(
            np.stack([tile_data, mask], axis=-1),
            transform,
            cval=0,
            output_shape=yx_chunk_shape,
            order=0,
            preserve_range=True,
        )
        warped_tiles.append(warped[..., 0].astype(dtype))
        warped_masks.append(warped[..., 1].astype(bool))

    warped_masks = np.nan_to_num(
        np.array(warped_masks), nan=False, posinf=True, neginf=False
    )
    return np.array(warped_tiles), warped_masks


def assemble_chunk(
    block_info=None, tile_map=None, warp_func=None, fuse_func=None, dtype=None
):
    """
    Assemble a chunk of the stitched image.

    Parameters
    ----------
    block_info :
        da.map_blocks block_info.
    tile_map :
        map of block positions to tiles.
    warp_func :
        function used to warp tiles.
    fuse_func :
        function used to fuse tiles.
    dtype :
        tile data type.

    Returns
    -------
        fused tiles corresponding to this block/chunk
    """
    chunk_location = block_info[None]["chunk-location"]
    chunk_shape = block_info[None]["chunk-shape"]
    tiles = tile_map[chunk_location]

    if len(tiles) > 0:
        warped_tiles, warped_masks = warp_func(
            block_info, chunk_shape[-2:], dtype, tiles
        )

        stitched_img = fuse_func(
            warped_tiles,
            warped_masks,
        ).astype(dtype=dtype)
        stitched_img = stitched_img[np.newaxis, np.newaxis, np.newaxis, ...]
    else:
        stitched_img = np.zeros(chunk_shape, dtype=dtype)

    return stitched_img


def shift_to_origin(tiles: list[Tile]) -> list[Tile]:
    """
    Shift tile positions such that the minimal position is (0, 0, 0, 0, 0).

    Parameters
    ----------
    tiles :
        List of tiles.

    Returns
    -------
    List of shifted tiles.
    """
    min_tile_origin = np.min([np.array(tile.get_position()) for tile in tiles], axis=0)
    shifted_tiles = copy(tiles)
    for tile in shifted_tiles:
        shifted_pos = np.array(tile.get_position()) - min_tile_origin
        tile.position = TilePosition(
            time=shifted_pos[0],
            channel=shifted_pos[1],
            z=shifted_pos[2],
            y=shifted_pos[3],
            x=shifted_pos[4],
        )
    return shifted_tiles
