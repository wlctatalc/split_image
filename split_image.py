import os
import cv2
import numpy as np
import argparse
from typing import List, Tuple

# 兼容中文路径的读写
def imread_unicode(path: str):
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)

def imwrite_unicode(path: str, img, ext: str = None, params=None):
    if params is None:
        params = []
    if ext is None:
        _, ext = os.path.splitext(path)
    ext = ext if ext else ".jpg"
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        return False
    try:
        buf.tofile(path)
        return True
    except Exception:
        return False

def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def is_image_file(name: str):
    ext = os.path.splitext(name)[1].lower()
    return ext in [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"]

def parse_pixels(pixels_str: str) -> List[int]:
    parts = [p.strip() for p in pixels_str.split(",") if p.strip() != ""]
    sizes = []
    for p in parts:
        if not p.isdigit():
            raise ValueError(f"像素值必须为正整数: {p}")
        val = int(p)
        if val <= 0:
            raise ValueError(f"像素值必须大于0: {p}")
        sizes.append(val)
    if not sizes:
        raise ValueError("像素列表为空")
    return sizes

def sizes_average(total: int, count: int) -> List[int]:
    base = total // count
    rem = total % count
    # 将余数分配到前 rem 份，每份 +1 像素
    return [base + (1 if i < rem else 0) for i in range(count)]

def build_slices(total: int, sizes: List[int], append_remainder: bool, clip_excess: bool) -> List[Tuple[int, int]]:
    sum_sizes = sum(sizes)
    slices = []
    start = 0

    if sum_sizes > total:
        if not clip_excess:
            raise ValueError(f"指定像素总和({sum_sizes})超过图像尺寸({total})，可加 --clip-excess 允许裁边")
        # 裁边：使用给定 sizes，但最后一个段落在边界处截断
        for i, sz in enumerate(sizes):
            end = start + sz
            if end > total:
                end = total
            if end <= start:
                break
            slices.append((start, end))
            start = end
            if start >= total:
                break
        return slices

    # sum_sizes <= total
    for sz in sizes:
        end = start + sz
        slices.append((start, end))
        start = end

    if sum_sizes < total and append_remainder:
        # 追加剩余部分为最后一段
        slices.append((start, total))

    # 过滤无效（零宽/零高）片段
    slices = [(s, e) for (s, e) in slices if e > s]
    return slices

def split_vertical(img: np.ndarray, sizes: List[int], append_remainder: bool, clip_excess: bool) -> List[np.ndarray]:
    h, w = img.shape[:2]
    ranges = build_slices(w, sizes, append_remainder, clip_excess)
    crops = [img[:, s:e] for (s, e) in ranges]
    return crops

def split_horizontal(img: np.ndarray, sizes: List[int], append_remainder: bool, clip_excess: bool) -> List[np.ndarray]:
    h, w = img.shape[:2]
    ranges = build_slices(h, sizes, append_remainder, clip_excess)
    crops = [img[s:e, :] for (s, e) in ranges]
    return crops

def process_one_image(in_path: str, out_dir: str, orientation: str, mode: str,
                      count: int, pixels: List[int], append_remainder: bool,
                      clip_excess: bool, out_ext: str, zero_pad: int):
    img = imread_unicode(in_path)
    if img is None:
        raise RuntimeError(f"无法读取图片: {in_path}")

    h, w = img.shape[:2]
    if mode == "average":
        if count <= 0:
            raise ValueError("average 模式需要 --count 且 > 0")
        if orientation == "vertical":
            sizes = sizes_average(w, count)
        else:
            sizes = sizes_average(h, count)
    else:
        # pixels 模式
        if not pixels:
            raise ValueError("pixels 模式需要 --pixels")
        sizes = pixels

    if orientation == "vertical":
        crops = split_vertical(img, sizes, append_remainder, clip_excess)
    else:
        crops = split_horizontal(img, sizes, append_remainder, clip_excess)

    base = os.path.splitext(os.path.basename(in_path))[0]
    ensure_dir(out_dir)

    digits = max(zero_pad, len(str(len(crops))))
    for i, crop in enumerate(crops, 1):
        out_name = f"{base}_part_{str(i).zfill(digits)}{out_ext}"
        out_path = os.path.join(out_dir, out_name)
        if not imwrite_unicode(out_path, crop):
            raise RuntimeError(f"写出失败: {out_path}")

    return len(crops), (h, w)

def main():
    parser = argparse.ArgumentParser(description="图片分割：横向或竖向，支持平均分割或按像素分割（中文路径兼容）")
    parser.add_argument("-i", "--input", required=True, help="输入文件或目录")
    parser.add_argument("-o", "--output", required=True, help="输出目录")
    parser.add_argument("--orientation", choices=["vertical", "horizontal"], default="vertical",
                        help="分割方向：vertical=竖向(按宽度切)，horizontal=横向(按高度切)")
    parser.add_argument("--mode", choices=["average", "pixels"], default="average",
                        help="average=平均分割; pixels=按像素列表分割")
    parser.add_argument("--count", type=int, default=2, help="average 模式：分割数量")
    parser.add_argument("--pixels", type=str, default="", help='pixels 模式：像素列表，用逗号分隔，如 "200,300,400"')
    parser.add_argument("--no-append-remainder", action="store_true",
                        help="像素和小于图像尺寸时，不自动追加剩余部分为最后一段（默认会追加）")
    parser.add_argument("--clip-excess", action="store_true",
                        help="像素和超过图像尺寸时，允许最后一段在边界处裁剪（默认报错）")
    parser.add_argument("--ext", type=str, default=".jpg", help="输出图片扩展名（.jpg/.png 等）")
    parser.add_argument("--zero-pad", type=int, default=2, help="输出序号的零填充位数下限（会根据数量自动放大）")
    args = parser.parse_args()

    in_path = args.input
    out_dir = args.output
    append_remainder = not args.no_append_remainder
    out_ext = args.ext if args.ext.startswith(".") else f".{args.ext}"

    pixels_list: List[int] = []
    if args.mode == "pixels":
        if not args.pixels:
            raise ValueError("pixels 模式需要 --pixels")
        pixels_list = parse_pixels(args.pixels)

    tasks = []
    if os.path.isdir(in_path):
        for name in sorted(os.listdir(in_path)):
            if not is_image_file(name):
                continue
            tasks.append(os.path.join(in_path, name))
    else:
        if not is_image_file(in_path):
            raise ValueError("输入必须是图片文件或包含图片的目录")
        tasks.append(in_path)

    ensure_dir(out_dir)

    total_images = 0
    for p in tasks:
        try:
            num, (h, w) = process_one_image(
                in_path=p,
                out_dir=out_dir,
                orientation=args.orientation,
                mode=args.mode,
                count=args.count,
                pixels=pixels_list,
                append_remainder=append_remainder,
                clip_excess=args.clip_excess,
                out_ext=out_ext,
                zero_pad=args.zero_pad,
            )
            total_images += 1
            print(f"[OK] {os.path.basename(p)} -> 切出 {num} 片 "
                  f"({args.orientation}, mode={args.mode})")
        except Exception as e:
            print(f"[FAIL] {os.path.basename(p)}: {e}")

    print(f"完成。处理图片数: {total_images} 输出目录: {out_dir}")

if __name__ == "__main__":
    main()