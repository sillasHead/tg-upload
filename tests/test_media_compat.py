import unittest
from pathlib import Path

import media_compat


def stream(
    index,
    codec_type,
    codec_name,
    *,
    profile=None,
    pix_fmt=None,
    language=None,
    title=None,
    is_default=False,
):
    return media_compat.StreamInfo(
        index=index,
        codec_type=codec_type,
        codec_name=codec_name,
        profile=profile,
        pix_fmt=pix_fmt,
        language=language,
        title=title,
        is_default=is_default,
    )


class MediaCompatTests(unittest.TestCase):
    def test_safe_h264_two_aac_lc_tracks_needs_no_conversion(self):
        video = stream(0, "video", "h264", profile="High", pix_fmt="yuv420p")
        por = stream(1, "audio", "aac", profile="LC", language="por", is_default=True)
        jpn = stream(2, "audio", "aac", profile="LC", language="jpn")
        probe = media_compat.MediaProbe(
            format_name="matroska,webm",
            video=video,
            audios=(por, jpn),
            subtitles=(),
            attachments=(),
        )

        plan = media_compat.build_plan(Path("episode.mkv"), probe)

        self.assertFalse(plan.needs_conversion)
        self.assertEqual([audio.index for audio in plan.selected_audios], [1, 2])

    def test_hevc_three_audio_tracks_builds_parasyte_compatible_plan(self):
        video = stream(0, "video", "hevc", profile="Main 10", pix_fmt="yuv420p10le")
        por = stream(1, "audio", "aac", profile="HE-AAC", language="por", is_default=True)
        jpn = stream(2, "audio", "aac", profile="LC", language="jpn")
        eng = stream(3, "audio", "aac", profile="LC", language="eng")
        probe = media_compat.MediaProbe(
            format_name="matroska,webm",
            video=video,
            audios=(por, jpn, eng),
            subtitles=(),
            attachments=(),
        )

        plan = media_compat.build_plan(Path("episode.mkv"), probe)

        self.assertTrue(plan.needs_conversion)
        self.assertTrue(plan.transcode_video)
        self.assertEqual([audio.index for audio in plan.selected_audios], [1, 2])
        self.assertEqual([audio.index for audio in plan.dropped_audios], [3])
        self.assertEqual(plan.transcode_audio_positions, (0,))

    def test_language_preference_controls_two_kept_tracks_and_order(self):
        video = stream(0, "video", "h264", profile="High", pix_fmt="yuv420p")
        por = stream(1, "audio", "aac", profile="LC", language="por", is_default=True)
        jpn = stream(2, "audio", "aac", profile="LC", language="jpn")
        eng = stream(3, "audio", "aac", profile="LC", language="eng")
        probe = media_compat.MediaProbe(
            format_name="matroska,webm",
            video=video,
            audios=(por, jpn, eng),
            subtitles=(),
            attachments=(),
        )

        plan = media_compat.build_plan(
            Path("episode.mkv"),
            probe,
            preferred_languages=("eng", "jpn"),
        )

        self.assertEqual([audio.index for audio in plan.selected_audios], [3, 2])
        self.assertEqual([audio.index for audio in plan.dropped_audios], [1])

    def test_ffmpeg_command_preserves_mkv_side_streams_and_metadata(self):
        video = stream(0, "video", "hevc", profile="Main 10", pix_fmt="yuv420p10le")
        por = stream(1, "audio", "aac", profile="HE-AAC", language="por", is_default=True)
        jpn = stream(2, "audio", "aac", profile="LC", language="jpn")
        eng = stream(3, "audio", "aac", profile="LC", language="eng")
        subtitle = stream(4, "subtitle", "ass", language="por")
        attachment = stream(5, "attachment", "ttf")
        probe = media_compat.MediaProbe(
            format_name="matroska,webm",
            video=video,
            audios=(por, jpn, eng),
            subtitles=(subtitle,),
            attachments=(attachment,),
        )
        plan = media_compat.build_plan(Path("episode.mkv"), probe)

        command = media_compat._build_ffmpeg_command(
            plan,
            Path("out.mkv"),
            "ffmpeg",
            "h264_nvenc",
        )
        joined = " ".join(command)

        self.assertIn("-map 0:1", joined)
        self.assertIn("-map 0:2", joined)
        self.assertNotIn("-map 0:3", joined)
        self.assertIn("-map 0:s?", joined)
        self.assertIn("-map 0:t?", joined)
        self.assertIn("-map_metadata 0", joined)
        self.assertIn("-map_chapters 0", joined)
        self.assertIn("-c:v h264_nvenc", joined)
        self.assertIn("-c:a:0 aac", joined)

    def test_non_mkv_is_not_modified(self):
        video = stream(0, "video", "hevc", profile="Main 10", pix_fmt="yuv420p10le")
        probe = media_compat.MediaProbe(
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
            video=video,
            audios=(),
            subtitles=(),
            attachments=(),
        )

        plan = media_compat.build_plan(Path("episode.mp4"), probe)

        self.assertFalse(plan.needs_conversion)
        self.assertFalse(plan.transcode_video)


if __name__ == "__main__":
    unittest.main()
