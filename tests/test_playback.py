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
