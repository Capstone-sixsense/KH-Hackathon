import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:khuthon/models/recommendation_models.dart';
import 'package:khuthon/screens/result_screen.dart';
import 'package:khuthon/services/recommendation_api.dart';
import 'package:khuthon/widgets/turntable_tonearm.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final TextEditingController _controller = TextEditingController();
  final RecommendationApi _api = RecommendationApi();
  final GlobalKey<_VinylLoadingDialogState> _vinylLoadingKey =
      GlobalKey<_VinylLoadingDialogState>();
  bool _isSearching = false;
  static const Duration _dialogCloseDelay = Duration(milliseconds: 220);
  static const int _maxHistoryCount = 8;
  static const List<Color> _historyPastelColors = [
    Color(0xFFFFF3B0),
    Color(0xFFFFE8A3),
    Color(0xFFFFF0C7),
    Color(0xFFF8E7A1),
    Color(0xFFFFECB5),
    Color(0xFFF6E7B5),
    Color(0xFFFFF6CC),
  ];
  final List<String> _searchHistory = [];

  void _appendKeyword(String keyword) {
    final current = _controller.text.trim();
    if (current.isEmpty) {
      _controller.text = keyword;
      return;
    }
    final tokens = current
        .split(',')
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
    if (tokens.contains(keyword)) {
      return;
    }
    // TODO: 추후 키워드 가중치/우선순위 확장 시 여기서 파싱 규칙 확장
    _controller.text = '$current, $keyword';
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _startMockSearch() async {
    if (_isSearching) {
      return;
    }
    final rawInput = _controller.text.trim();
    final keyword = rawInput.isEmpty ? '너랑 나, IU' : rawInput;
    final query = _buildQuery(keyword);
    setState(() => _isSearching = true);
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => VinylLoadingDialog(key: _vinylLoadingKey),
    );
    try {
      final response = await _api.recommend(RecommendRequest(query: query));
      if (!mounted) {
        return;
      }
      final hasAnyResult =
          response.similar.isNotEmpty ||
          response.reverse.isNotEmpty ||
          response.opposite.isNotEmpty ||
          response.hidden.isNotEmpty;
      if (!hasAnyResult) {
        await _awaitVinylFailureAnimationOrFallback();
        if (!mounted) {
          return;
        }
        Navigator.of(context, rootNavigator: true).pop();
        await Future<void>.delayed(_dialogCloseDelay);
        if (!mounted) {
          return;
        }
        await _showSearchNotFoundDialog();
        return;
      }
      await _closeLoadingDialogWithDelay();
      if (!mounted) {
        return;
      }
      if (rawInput.isNotEmpty) {
        _recordSearchHistory(rawInput);
      }
      await Navigator.of(context).push(
        PageRouteBuilder<void>(
          transitionDuration: const Duration(milliseconds: 420),
          reverseTransitionDuration: const Duration(milliseconds: 300),
          pageBuilder: (_, animation, secondaryAnimation) =>
              ResultScreen(keyword: keyword, response: response),
          transitionsBuilder: (_, animation, secondaryAnimation, child) {
            final curvedAnimation = CurvedAnimation(
              parent: animation,
              curve: Curves.easeOutCubic,
              reverseCurve: Curves.easeInCubic,
            );
            final scaleAnimation = Tween<double>(begin: 0.96, end: 1).animate(
              CurvedAnimation(
                parent: animation,
                curve: Curves.easeOutCubic,
                reverseCurve: Curves.easeInCubic,
              ),
            );
            return FadeTransition(
              opacity: curvedAnimation,
              child: ScaleTransition(scale: scaleAnimation, child: child),
            );
          },
        ),
      );
    } catch (e) {
      if (!mounted) {
        return;
      }
      await _awaitVinylFailureAnimationOrFallback();
      if (!mounted) {
        return;
      }
      Navigator.of(context, rootNavigator: true).pop();
      await Future<void>.delayed(_dialogCloseDelay);
      if (!mounted) {
        return;
      }
      await _showSearchNotFoundDialog();
    } finally {
      if (mounted) {
        setState(() => _isSearching = false);
      }
    }
  }

  Future<void> _awaitVinylFailureAnimationOrFallback() async {
    final vinyl = _vinylLoadingKey.currentState;
    if (vinyl != null) {
      await vinyl.playFailureSequence();
    } else {
      await Future<void>.delayed(const Duration(milliseconds: 600));
    }
  }

  Future<void> _closeLoadingDialogWithDelay() async {
    Navigator.of(context, rootNavigator: true).pop();
    // 다이얼로그 종료 애니메이션이 끝난 뒤 다음 전환을 시작한다.
    await Future<void>.delayed(_dialogCloseDelay);
  }

  String _buildQuery(String keyword) {
    final dash = keyword
        .split('-')
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
    if (dash.length >= 2) {
      return dash.join(' ');
    }
    final comma = keyword
        .split(',')
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
    if (comma.length >= 2) {
      return comma.join(' ');
    }
    return keyword.trim();
  }

  void _recordSearchHistory(String keyword) {
    final normalized = keyword.trim();
    if (normalized.isEmpty) {
      return;
    }
    setState(() {
      _searchHistory.removeWhere(
        (item) => item.toLowerCase() == normalized.toLowerCase(),
      );
      _searchHistory.insert(0, normalized);
      if (_searchHistory.length > _maxHistoryCount) {
        _searchHistory.removeRange(_maxHistoryCount, _searchHistory.length);
      }
    });
  }

  Future<void> _showSearchNotFoundDialog() async {
    return showDialog<void>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('검색 실패'),
          content: const Text('음악을 찾을 수 없어요. 다시 입력해주세요.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('OK'),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final shortest = math.min(
              constraints.maxWidth,
              constraints.maxHeight,
            );
            final availableRadius = math.min(
              constraints.maxWidth * 0.48,
              constraints.maxHeight * 0.44,
            );
            final recordRadius = math.min(
              (shortest * 0.43).clamp(170.0, 430.0).toDouble(),
              availableRadius,
            );
            final labelSize = math
                .min(
                  (recordRadius * 1.08).clamp(300.0, 460.0).toDouble(),
                  math.min(
                    constraints.maxWidth - 40,
                    constraints.maxHeight * 0.72,
                  ),
                )
                .toDouble();
            final center = Offset(
              constraints.maxWidth * 0.5,
              constraints.maxHeight * 0.52,
            );

            return Stack(
              clipBehavior: Clip.none,
              children: [
                Positioned.fill(
                  child: CustomPaint(
                    painter: _HomeTurntablePainter(
                      center: center,
                      radius: recordRadius,
                    ),
                  ),
                ),
                Positioned(
                  left: center.dx + (recordRadius * 0.31),
                  top: center.dy - (recordRadius * 0.74),
                  child: IgnorePointer(
                    child: TurntableTonearm(
                      size: recordRadius * 0.62,
                      accent: const Color(0xFFF472B6),
                      opacity: 0.94,
                      rotation: -0.06,
                    ),
                  ),
                ),
                Positioned(
                  left: center.dx - (labelSize / 2),
                  top: center.dy - (labelSize / 2),
                  child: _buildHomeRecordLabel(labelSize),
                ),
                ..._buildHistoryPostIts(
                  constraints: constraints,
                  center: center,
                  recordRadius: recordRadius,
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _buildHomeRecordLabel(double labelSize) {
    final contentWidth = labelSize * 0.75;
    final compact = labelSize < 340;
    final titleFontSize = compact ? 34.0 : 42.0;
    final subtitleFontSize = compact ? 11.5 : 13.0;
    final verticalGap = compact ? 8.0 : 14.0;
    return Container(
      width: labelSize,
      height: labelSize,
      padding: EdgeInsets.symmetric(
        horizontal: labelSize * 0.12,
        vertical: labelSize * 0.1,
      ),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: const RadialGradient(
          colors: [Color(0xFFF4E3BF), Color(0xFFD1AC68), Color(0xFF7B5B2D)],
          stops: [0, 0.7, 1],
        ),
        border: Border.all(
          color: const Color(0xFFFFF3D2).withValues(alpha: 0.82),
          width: 2,
        ),
        boxShadow: const [
          BoxShadow(
            color: Color(0x77000000),
            blurRadius: 34,
            offset: Offset(0, 16),
          ),
        ],
      ),
      child: Center(
        child: SingleChildScrollView(
          physics: const NeverScrollableScrollPhysics(),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ShaderMask(
                shaderCallback: (bounds) => const LinearGradient(
                  colors: [Color(0xFF2A1D10), Color(0xFF6D4A22)],
                ).createShader(bounds),
                child: Text(
                  'Side-B',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: titleFontSize,
                    fontWeight: FontWeight.w800,
                    color: Colors.white,
                    fontFamily: 'OK_Mallang_Font',
                  ),
                ),
              ),
              SizedBox(height: compact ? 4 : 8),
              Text(
                '들리지 않던 쪽으로, 취향의 이면을 넘기다',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: const Color(0xFF4B371C),
                  fontSize: subtitleFontSize,
                  fontWeight: FontWeight.w700,
                ),
              ),
              SizedBox(height: compact ? 10 : labelSize * 0.052),
              SizedBox(
                width: contentWidth,
                height: compact ? 44 : null,
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF15151D).withValues(alpha: 0.92),
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(
                      color: Colors.white.withValues(alpha: 0.14),
                    ),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 14),
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      ValueListenableBuilder<TextEditingValue>(
                        valueListenable: _controller,
                        builder: (context, value, child) {
                          if (value.text.isNotEmpty) {
                            return const SizedBox.shrink();
                          }
                          return IgnorePointer(child: child);
                        },
                        child: const Padding(
                          padding: EdgeInsets.symmetric(horizontal: 24),
                          child: FittedBox(
                            fit: BoxFit.scaleDown,
                            child: Text(
                              '키워드로 음악을 탐색해 보세요',
                              maxLines: 1,
                              style: TextStyle(
                                color: Color(0xFFA1A1AA),
                                fontSize: 15,
                              ),
                            ),
                          ),
                        ),
                      ),
                      TextField(
                        controller: _controller,
                        readOnly: _isSearching,
                        textInputAction: TextInputAction.search,
                        onSubmitted:
                            _isSearching ? null : (_) => _startMockSearch(),
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          color: Color(0xFFF4F4F5),
                          fontSize: 15,
                        ),
                        decoration: const InputDecoration(
                          border: InputBorder.none,
                          prefixIcon: Icon(
                            Icons.search_rounded,
                            color: Color(0xFF94A3B8),
                          ),
                          prefixIconConstraints: BoxConstraints(
                            minWidth: 40,
                            minHeight: 40,
                          ),
                          suffixIcon: SizedBox(width: 40),
                          suffixIconConstraints: BoxConstraints(
                            minWidth: 40,
                            minHeight: 40,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              SizedBox(height: verticalGap),
              SizedBox(height: compact ? 8 : labelSize * 0.04),
              SizedBox(
                width: math.min(contentWidth * 0.62, 220),
                child: FilledButton(
                  onPressed: _isSearching ? null : _startMockSearch,
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF0F766E),
                    foregroundColor: Colors.white,
                    elevation: 0,
                    padding: EdgeInsets.symmetric(vertical: compact ? 12 : 15),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                  ),
                  child: const Text(
                    '탐색 시작',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _buildHistoryPostIts({
    required BoxConstraints constraints,
    required Offset center,
    required double recordRadius,
  }) {
    if (_searchHistory.isEmpty) {
      return const [];
    }

    final sideSpace = ((constraints.maxWidth - (recordRadius * 2)) / 2) - 20;
    final useSideColumns = sideSpace >= 128;
    final noteWidth = useSideColumns
        ? sideSpace.clamp(150.0, 230.0).toDouble()
        : (constraints.maxWidth * 0.4).clamp(132.0, 190.0).toDouble();
    final notes = _searchHistory.reversed.take(useSideColumns ? 8 : 4).toList();
    final leftX = (center.dx - recordRadius - noteWidth - 18)
        .clamp(12.0, constraints.maxWidth - noteWidth - 12)
        .toDouble();
    final rightX = (center.dx + recordRadius + 18)
        .clamp(12.0, constraints.maxWidth - noteWidth - 12)
        .toDouble();
    final fallbackLeftX = (center.dx - noteWidth - 14)
        .clamp(12.0, constraints.maxWidth - noteWidth - 12)
        .toDouble();
    final fallbackRightX = (center.dx + 14)
        .clamp(12.0, constraints.maxWidth - noteWidth - 12)
        .toDouble();
    final baseY = (center.dy - (recordRadius * 0.86))
        .clamp(18.0, constraints.maxHeight - 70)
        .toDouble();
    final leftColumnCapacity = useSideColumns ? 4 : 2;
    const angles = [-0.08, 0.055, -0.045, 0.075, -0.065, 0.045, -0.035, 0.06];
    const offsets = [0.0, 12.0, -5.0, 15.0, 2.0, -7.0, 11.0, -3.0];

    return List.generate(notes.length, (index) {
      final leftSide = index < leftColumnCapacity;
      final sideIndex = leftSide ? index : index - leftColumnCapacity;
      final x = useSideColumns
          ? (leftSide ? leftX : rightX)
          : (leftSide ? fallbackLeftX : fallbackRightX);
      final y = (baseY + (sideIndex * 86) + offsets[index % offsets.length])
          .clamp(16.0, constraints.maxHeight - 76)
          .toDouble();
      return Positioned(
        left: x,
        top: y,
        child: _HistoryPostIt(
          text: notes[index],
          width: noteWidth,
          color: _historyPastelColors[index % _historyPastelColors.length],
          angle: angles[index % angles.length],
          enabled: !_isSearching,
          onTap: () => setState(() => _appendKeyword(notes[index])),
        ),
      );
    });
  }
}

class _HistoryPostIt extends StatelessWidget {
  const _HistoryPostIt({
    required this.text,
    required this.width,
    required this.color,
    required this.angle,
    required this.enabled,
    required this.onTap,
  });

  final String text;
  final double width;
  final Color color;
  final double angle;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: angle,
      child: GestureDetector(
        onTap: enabled ? onTap : null,
        child: AnimatedOpacity(
          duration: const Duration(milliseconds: 200),
          opacity: enabled ? 1 : 0.45,
          child: Container(
            width: width,
            constraints: const BoxConstraints(minHeight: 46),
            padding: const EdgeInsets.fromLTRB(16, 11, 14, 10),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.9),
              borderRadius: BorderRadius.circular(5),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.52),
                width: 1,
              ),
              boxShadow: const [
                BoxShadow(
                  color: Color(0x66000000),
                  blurRadius: 12,
                  offset: Offset(0, 7),
                ),
              ],
            ),
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                Positioned(
                  left: width * 0.32,
                  top: -19,
                  child: Transform.rotate(
                    angle: -angle * 0.65,
                    child: Container(
                      width: width * 0.34,
                      height: 16,
                      decoration: BoxDecoration(
                        color: const Color(0xFFFDE68A).withValues(alpha: 0.5),
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                  ),
                ),
                Text(
                  text,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Color(0xFF1F2937),
                    fontFamily: 'OK_Mallang_Font',
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _HomeTurntablePainter extends CustomPainter {
  const _HomeTurntablePainter({required this.center, required this.radius});

  final Offset center;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawCircle(
      center.translate(0, 18),
      radius * 1.02,
      Paint()..color = Colors.black.withValues(alpha: 0.42),
    );
    canvas.drawCircle(
      center,
      radius,
      Paint()
        ..shader = const RadialGradient(
          colors: [Color(0xFF30303A), Color(0xFF111118), Color(0xFF050507)],
          stops: [0.0, 0.46, 1.0],
        ).createShader(Rect.fromCircle(center: center, radius: radius)),
    );
    canvas.drawCircle(
      center,
      radius,
      Paint()
        ..color = Colors.white.withValues(alpha: 0.12)
        ..strokeWidth = 1.2
        ..style = PaintingStyle.stroke,
    );

    for (var i = 0; i < 16; i++) {
      final grooveRadius = radius * (0.2 + (i * 0.048));
      canvas.drawCircle(
        center,
        grooveRadius,
        Paint()
          ..color = Colors.white.withValues(alpha: i.isEven ? 0.052 : 0.026)
          ..strokeWidth = i.isEven ? 1.0 : 0.7
          ..style = PaintingStyle.stroke,
      );
    }

    canvas.drawCircle(
      center,
      radius * 0.055,
      Paint()..color = const Color(0xFF111827),
    );
    canvas.drawCircle(
      center,
      radius * 0.024,
      Paint()..color = const Color(0xFF2DD4BF),
    );
  }

  @override
  bool shouldRepaint(covariant _HomeTurntablePainter oldDelegate) {
    return oldDelegate.center != center || oldDelegate.radius != radius;
  }
}

class VinylLoadingDialog extends StatefulWidget {
  const VinylLoadingDialog({super.key});

  @override
  State<VinylLoadingDialog> createState() => _VinylLoadingDialogState();
}

class _VinylLoadingDialogState extends State<VinylLoadingDialog>
    with TickerProviderStateMixin {
  late final AnimationController _discController;
  late final AnimationController _failureController;
  late final Animation<double> _failureScale;
  Timer? _lineTimer;
  int _lineIndex = 0;
  bool _failure = false;

  static const _lines = [
    '음악 탐색 중...',
    '당신의 취향 바깥을 여행하는 중...',
    '숨겨진 트랙을 찾고 있어요...',
    'Side-B 감성 매칭 중...',
  ];

  /// 탐색 실패 시 디스크 정지 + X 표시 애니메이션 후 종료 대기.
  Future<void> playFailureSequence() async {
    if (!mounted || _failure) {
      return;
    }
    _lineTimer?.cancel();
    _discController.stop();
    setState(() => _failure = true);
    await _failureController.forward(from: 0);
    await Future<void>.delayed(const Duration(milliseconds: 200));
  }

  @override
  void initState() {
    super.initState();
    _discController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1700),
    )..repeat();

    _failureController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 520),
    );
    _failureScale = CurvedAnimation(
      parent: _failureController,
      curve: Curves.elasticOut,
    );

    _lineTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      if (!mounted || _failure) {
        return;
      }
      setState(() {
        _lineIndex = (_lineIndex + 1) % _lines.length;
      });
    });
  }

  @override
  void dispose() {
    _lineTimer?.cancel();
    _discController.dispose();
    _failureController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: const Color(0xFF111119),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: AbsorbPointer(
        absorbing: _failure,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 120,
                height: 120,
                child: Stack(
                  alignment: Alignment.center,
                  clipBehavior: Clip.none,
                  children: [
                    AnimatedBuilder(
                      animation: _discController,
                      builder: (_, child) {
                        return Transform.rotate(
                          angle: _discController.value * 2 * math.pi,
                          child: child,
                        );
                      },
                      child: Stack(
                        alignment: Alignment.center,
                        children: [
                          Container(
                            width: 100,
                            height: 100,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              gradient: const RadialGradient(
                                colors: [Color(0xFF34343A), Color(0xFF0D0D12)],
                                stops: [0.25, 1],
                              ),
                              border: Border.all(
                                color: const Color(
                                  0xFF4B5563,
                                ).withValues(alpha: 0.3),
                                width: 1,
                              ),
                              boxShadow: const [
                                BoxShadow(
                                  color: Color(0x66000000),
                                  blurRadius: 12,
                                  offset: Offset(0, 6),
                                ),
                              ],
                            ),
                          ),
                          Container(
                            width: 78,
                            height: 78,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: Colors.white.withValues(alpha: 0.09),
                                width: 2,
                              ),
                            ),
                          ),
                          Container(
                            width: 52,
                            height: 52,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: Colors.white.withValues(alpha: 0.08),
                                width: 2,
                              ),
                            ),
                          ),
                          Container(
                            width: 18,
                            height: 18,
                            decoration: const BoxDecoration(
                              shape: BoxShape.circle,
                              color: Color(0xFF111827),
                            ),
                          ),
                          Container(
                            width: 8,
                            height: 8,
                            decoration: const BoxDecoration(
                              shape: BoxShape.circle,
                              color: Color(0xFF2DD4BF),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (_failure)
                      Positioned.fill(
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: Colors.black.withValues(alpha: 0.45),
                          ),
                          child: Center(
                            child: ScaleTransition(
                              scale: _failureScale,
                              child: Container(
                                width: 56,
                                height: 56,
                                decoration: const BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: Color(0xFFDC2626),
                                  boxShadow: [
                                    BoxShadow(
                                      color: Color(0x66000000),
                                      blurRadius: 12,
                                      offset: Offset(0, 4),
                                    ),
                                  ],
                                ),
                                child: const Icon(
                                  Icons.close_rounded,
                                  color: Colors.white,
                                  size: 36,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    Positioned(
                      right: 0,
                      top: 4,
                      child: TurntableTonearm(
                        size: 82,
                        accent: const Color(0xFFF472B6),
                        opacity: 0.95,
                        rotation: -0.18,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              SizedBox(
                width: 240,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _failure ? '탐색 실패' : '분석 중',
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 12),
                    AnimatedSwitcher(
                      duration: const Duration(milliseconds: 260),
                      child: Text(
                        _failure
                            ? '조건에 맞는 곡을 찾지 못했어요.'
                            : _lines[_lineIndex],
                        key: ValueKey('${_failure}_$_lineIndex'),
                        style: const TextStyle(
                          color: Color(0xFFA1A1AA),
                          height: 1.4,
                          fontSize: 13,
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    if (_failure)
                      const LinearProgressIndicator(
                        value: 0,
                        color: Color(0xFFDC2626),
                        backgroundColor: Color(0xFF27272A),
                      )
                    else
                      const LinearProgressIndicator(
                        color: Color(0xFF2DD4BF),
                        backgroundColor: Color(0xFF27272A),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
