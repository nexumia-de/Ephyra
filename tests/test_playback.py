import pytest

from ephyra import playback


ITEM = {"Id": "abc", "MediaType": "Video"}


def test_direct_play_path():
    info = {"PlaySessionId": "s", "MediaSources": [{
        "Id": "src", "SupportsDirectPlay": True, "ETag": "e",
        "RunTimeTicks": 600_000_000}]}
    stream = playback.choose(ITEM, info, "dev", "tok")
    assert stream.method == playback.DIRECT_PLAY
    assert stream.path.startswith("/Videos/abc/stream?static=true&mediaSourceId=src")
    assert "tag=e" in stream.path and "tok" not in stream.path
    assert stream.duration == 60
    report = stream.report(12.5, paused=True)
    assert report["PositionTicks"] == 125_000_000 and report["IsPaused"]


def test_transcode_path():
    info = {"PlaySessionId": "s", "MediaSources": [{
        "Id": "src", "SupportsDirectPlay": False, "SupportsDirectStream": False,
        "SupportsTranscoding": True,
        "TranscodingUrl": "/videos/abc/master.m3u8?MediaSourceId=src"}]}
    stream = playback.choose(ITEM, info, "dev", "tok")
    assert stream.method == playback.TRANSCODE
    assert stream.path == "/videos/abc/master.m3u8?MediaSourceId=src"


def test_transcode_url_loses_the_token():
    info = {"MediaSources": [{
        "Id": "src", "SupportsDirectPlay": False, "SupportsTranscoding": True,
        "TranscodingUrl": "/videos/abc/master.m3u8?MediaSourceId=src&ApiKey=secret&api_key=x"}]}
    stream = playback.choose(ITEM, info, "dev", "secret")
    assert stream.path == "/videos/abc/master.m3u8?MediaSourceId=src"


def test_user_may_not_transcode():
    # MediaSourceManager: SupportsTranscoding = EnableVideoPlaybackTranscoding
    info = {"MediaSources": [{"Id": "src", "SupportsDirectPlay": False,
                              "SupportsDirectStream": False,
                              "SupportsTranscoding": False}]}
    with pytest.raises(playback.NoPlayableSource, match="requires transcoding"):
        playback.choose(ITEM, info, "dev", "tok")


def test_audio_path():
    info = {"MediaSources": [{"Id": "a", "SupportsDirectPlay": True}]}
    stream = playback.choose({"Id": "a", "MediaType": "Audio"}, info, "d", "t")
    assert stream.path.startswith("/Audio/a/stream?")


def test_no_source():
    with pytest.raises(playback.NoPlayableSource, match="may not play"):
        playback.choose(ITEM, {"MediaSources": [], "ErrorCode": "NotAllowed"}, "d", "t")


def test_profile_caps_bitrate():
    profile = playback.device_profile(4_000_000)
    assert profile["MaxStreamingBitrate"] == 4_000_000
    assert profile["TranscodingProfiles"][0]["Protocol"] == "hls"
    assert playback.device_profile(0)["MaxStreamingBitrate"] > 100_000_000


def test_details_name_file_and_server_answer():
    info = {"ErrorCode": "NoCompatibleStream", "MediaSources": [{
        "Container": "mkv", "SupportsDirectPlay": False,
        "SupportsTranscoding": False,
        "MediaStreams": [{"Type": "Video", "Codec": "hevc"},
                         {"Type": "Audio", "Codec": "eac3"}]}]}
    assert playback.describe(info) == (
        "mkv · hevc · eac3 · direct play no · convert not allowed · "
        "converted stream none · error NoCompatibleStream")
    with pytest.raises(playback.NoPlayableSource) as e:
        playback.choose(ITEM, info, "d", "t")
    assert "hevc" in e.value.details


def test_gstreamer_reason_is_short():
    from ephyra.player import gst_reason
    message = ("Error from element /GstPlayBin:playbin/GstURIDecodeBin:"
               "uridecodebin0/GstTypeFindElement:typefindelement0: Could not "
               "determine type of stream.\nCould not determine type of stream."
               "\n../plugins/elements/gsttypefindelement.c(1025): gst_type_find")
    assert gst_reason(message) == "Could not determine type of stream."
    assert gst_reason("No decoder available for type 'video/x-h265'.") == (
        "No decoder available for type 'video/x-h265'.")


TRACKS = [
    {"Index": 0, "Type": "Video", "Codec": "vp8"},
    {"Index": 1, "Type": "Audio", "Language": "eng", "DisplayTitle": "English - Vorbis"},
    {"Index": 2, "Type": "Audio", "Language": "ger", "DisplayTitle": "German - Vorbis"},
    {"Index": 3, "Type": "Audio", "IsExternal": True, "DisplayTitle": "Commentary"},
    {"Index": 4, "Type": "Subtitle", "DisplayTitle": "English - SRT",
     "DeliveryMethod": "External",
     "DeliveryUrl": "/Videos/abc/src/Subtitles/4/0/Stream.srt?ApiKey=tok"},
    {"Index": 5, "Type": "Subtitle", "DisplayTitle": "German - PGS",
     "DeliveryMethod": "Encode"},
    {"Index": 6, "Type": "Subtitle", "DisplayTitle": "Hidden", "DeliveryMethod": "Drop"},
]


def test_subtitles_come_as_srt_files():
    profile = playback.device_profile(0)
    assert profile["SubtitleProfiles"] == [{"Format": "srt", "Method": "External"}]


def test_tracks_and_choice():
    info = {"PlaySessionId": "s", "MediaSources": [{
        "Id": "src", "SupportsDirectPlay": True, "MediaStreams": TRACKS,
        "DefaultAudioStreamIndex": 2, "DefaultSubtitleStreamIndex": 4}]}
    stream = playback.choose(ITEM, info, "dev", "tok")
    source = stream.source
    # External audio files are not in the played stream.
    assert playback.audio_tracks(source) == [(1, "English - Vorbis"),
                                             (2, "German - Vorbis")]
    assert playback.subtitle_tracks(source) == [(4, "English - SRT"),
                                                (5, "German - PGS (converted on the server)")]
    assert stream.audio_position == 1
    assert stream.subtitle_path == "/Videos/abc/src/Subtitles/4/0/Stream.srt"
    report = stream.report(1)
    assert report["AudioStreamIndex"] == 2 and report["SubtitleStreamIndex"] == 4
    stream.subtitle_index = 5
    assert stream.subtitle_path is None
    assert playback.subtitle_method(source, 5) == "Encode"
    assert playback.subtitle_method(source, -1) is None
    stream.subtitle_index = -1
    assert stream.subtitle_path is None


def test_blu_ray_audio_plays_directly():
    # avdec_truehd and avdec_dca are in the GNOME 51 runtime (docs/playback.md).
    video = playback.device_profile(0)["DirectPlayProfiles"][0]
    codecs = video["AudioCodec"].split(",")
    assert "truehd" in codecs and "dts" in codecs


def test_burned_in_default_is_noticed():
    def info(default):
        return {"MediaSources": [{"MediaStreams": TRACKS,
                                  "DefaultSubtitleStreamIndex": default}]}
    assert playback.burns_in_default(info(5))          # PGS: Encode
    assert not playback.burns_in_default(info(4))      # SRT: External
    assert not playback.burns_in_default(info(-1))
    assert not playback.burns_in_default(info(None))
    assert not playback.burns_in_default({"MediaSources": []})


def test_stop_report_of_a_stream_that_never_played():
    stream = playback.choose(ITEM, {"PlaySessionId": "s", "MediaSources": [{
        "Id": "src", "SupportsDirectPlay": True}]}, "dev", "tok")
    payload = stream.stop_report(90, failed=True)
    # Failed: the server keeps the resume position (SessionManager).
    assert payload["Failed"] and payload["PlaySessionId"] == "s"
    assert payload["PositionTicks"] == 900_000_000
    assert "Failed" not in stream.stop_report(90)
