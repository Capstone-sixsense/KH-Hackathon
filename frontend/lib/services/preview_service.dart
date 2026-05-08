import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:khuthon/services/recommendation_api.dart';

enum PreviewLoadState { idle, loading, playing, paused }

class PreviewService {
  PreviewService._() {
    _player.onPlayerStateChanged.listen((s) {
      if (s == PlayerState.completed || s == PlayerState.stopped) {
        _loadState = PreviewLoadState.idle;
        _currentKey = null;
        _currentTrackName = null;
        _currentArtist = null;
        _currentAlbumArt = null;
        _keyCtl.add(null);
      } else if (s == PlayerState.playing) {
        _loadState = PreviewLoadState.playing;
        _keyCtl.add(_currentKey);
      } else if (s == PlayerState.paused) {
        _loadState = PreviewLoadState.paused;
        _keyCtl.add(_currentKey);
      }
    });
  }

  static final PreviewService instance = PreviewService._();

  final AudioPlayer _player = AudioPlayer();
  final _keyCtl = StreamController<String?>.broadcast();

  PreviewLoadState _loadState = PreviewLoadState.idle;
  String? _currentKey;
  String? _currentTrackName;
  String? _currentArtist;
  String? _currentAlbumArt;

  Stream<String?> get keyStream => _keyCtl.stream;
  Stream<Duration> get positionStream => _player.onPositionChanged;

  PreviewLoadState get loadState => _loadState;
  String? get currentKey => _currentKey;
  String? get currentTrackName => _currentTrackName;
  String? get currentArtist => _currentArtist;
  String? get currentAlbumArt => _currentAlbumArt;

  static String buildKey(String track, String artist) => '$artist::$track';

  Future<void> toggle({
    required String track,
    required String artist,
    String? albumArtUrl,
  }) async {
    final key = buildKey(track, artist);

    // 같은 트랙: 재생/일시정지 토글
    if (_currentKey == key) {
      if (_loadState == PreviewLoadState.playing) {
        await _player.pause();
      } else if (_loadState == PreviewLoadState.paused) {
        await _player.resume();
      }
      return;
    }

    // 다른 트랙: 기존 정지 후 새로 시작
    await _player.stop();
    _loadState = PreviewLoadState.loading;
    _currentKey = key;
    _currentTrackName = track;
    _currentArtist = artist;
    _currentAlbumArt = albumArtUrl;
    _keyCtl.add(key);

    final base = RecommendationApi.resolveBaseUrl();
    final streamUrl =
        '$base/preview/stream'
        '?track=${Uri.encodeComponent(track)}'
        '&artist=${Uri.encodeComponent(artist)}';

    try {
      await _player.play(UrlSource(streamUrl));
    } catch (_) {
      _loadState = PreviewLoadState.idle;
      _currentKey = null;
      _keyCtl.add(null);
    }
  }

  Future<void> stop() async {
    await _player.stop();
    _loadState = PreviewLoadState.idle;
    _currentKey = null;
    _currentTrackName = null;
    _currentArtist = null;
    _currentAlbumArt = null;
    _keyCtl.add(null);
  }
}
