export const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const VIDEO_TYPES = ["video/mp4", "video/webm"];

export function uploadErrorCode(file, { allowVideo = false } = {}) {
  if (!file || !file.size) return "media_invalid";
  if (IMAGE_TYPES.includes(file.type))
    return file.size > 8 * 1024 * 1024 ? "media_image_size" : null;
  if (allowVideo && VIDEO_TYPES.includes(file.type))
    return file.size > 40 * 1024 * 1024 ? "media_video_size" : null;
  return allowVideo ? "media_invalid" : "media_image_required";
}
