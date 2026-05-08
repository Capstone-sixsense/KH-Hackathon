import 'dart:async';
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:khuthon/models/recommendation_models.dart';
import 'package:khuthon/screens/result_screen.dart';
import 'package:khuthon/services/recommendation_api.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final TextEditingController _controller = TextEditingController();
  final RecommendationApi _api = RecommendationApi();
  static const Duration _dialogCloseDelay = Duration(milliseconds: 220);

  void _appendKeyword(String keyword) {
    final current = _controller.text.trim();
    if (current.isEmpty) {
      _controller.text = keyword;
      return;
    }
    final tokens = current.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
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
    final keyword = _controller.text.trim().isEmpty ? '너랑 나, IU' : _controller.text.trim();
    final parsed = _parseInput(keyword);
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const VinylLoadingDialog(),
    );
    try {
      final response = await _api.recommend(
        RecommendRequest(trackName: parsed.$1, artist: parsed.$2),
      );
      if (!mounted) {
        return;
      }
      await _closeLoadingDialogWithDelay();
      if (!mounted) {
        return;
      }
      await Navigator.of(context).push(
        PageRouteBuilder<void>(
          transitionDuration: const Duration(milliseconds: 760),
          reverseTransitionDuration: const Duration(milliseconds: 560),
          pageBuilder: (_, animation, secondaryAnimation) =>
              ResultScreen(keyword: keyword, response: response),
          transitionsBuilder: (_, animation, secondaryAnimation, child) {
            final slideAnimation = Tween<Offset>(
              begin: const Offset(0.12, 0),
              end: Offset.zero,
            ).animate(
              CurvedAnimation(
                parent: animation,
                curve: Curves.easeInOutCubicEmphasized,
              ),
            );
            final fadeAnimation = CurvedAnimation(
              parent: animation,
              curve: Curves.easeInOutCubicEmphasized,
            );
            return FadeTransition(
              opacity: fadeAnimation,
              child: SlideTransition(
                position: slideAnimation,
                child: child,
              ),
            );
          },
        ),
      );
    } catch (e) {
      if (!mounted) {
        return;
      }
      await _closeLoadingDialogWithDelay();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('추천 결과를 불러오지 못했습니다: $e')),
      );
    }
  }

  Future<void> _closeLoadingDialogWithDelay() async {
    Navigator.of(context, rootNavigator: true).pop();
    // 다이얼로그 종료 애니메이션이 끝난 뒤 다음 전환을 시작한다.
    await Future<void>.delayed(_dialogCloseDelay);
  }

  (String, String) _parseInput(String keyword) {
    final dash = keyword.split('-').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
    if (dash.length >= 2) {
      return (dash.first, dash[1]);
    }
    final comma = keyword.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
    if (comma.length >= 2) {
      return (comma.first, comma[1]);
    }
    return (keyword.trim(), 'IU');
  }

  @override
  Widget build(BuildContext context) {
    const suggestions = ['새벽 감성', '브릿팝', '시티팝', '로파이', '소수 취향'];
    final screenWidth = MediaQuery.of(context).size.width;
    final horizontalInset = math.min(500.0, screenWidth * 0.12);
    final contentWidth = math.max(320.0, screenWidth - (horizontalInset * 2));
    final maxContentWidth = math.min(contentWidth, 560.0);
    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            Positioned(
              left: -100,
              top: -80,
              child: _GlowOrb(size: 280, color: const Color(0xFF2DD4BF).withValues(alpha: 0.18)),
            ),
            Positioned(
              right: -120,
              bottom: -80,
              child: _GlowOrb(size: 320, color: const Color(0xFF4B5563).withValues(alpha: 0.18)),
            ),
            Center(
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: horizontalInset, vertical: 20),
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: maxContentWidth),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(28),
                    child: BackdropFilter(
                      filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 34),
                        decoration: BoxDecoration(
                          color: const Color(0xFF12121A).withValues(alpha: 0.82),
                          borderRadius: BorderRadius.circular(28),
                          border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
                          boxShadow: const [BoxShadow(color: Color(0x66000000), blurRadius: 28, offset: Offset(0, 14))],
                        ),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            ShaderMask(
                              shaderCallback: (bounds) => const LinearGradient(
                                colors: [Color(0xFFE5E7EB), Color(0xFF6B7280)],
                              ).createShader(bounds),
                              child: const Text(
                                'Side-B',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 42,
                                  fontWeight: FontWeight.w800,
                                  color: Colors.white,
                                  fontFamily: 'OK_Mallang_Font',
                                ),
                              ),
                            ),
                            const SizedBox(height: 10),
                            const Text(
                              '메이저 바깥의 음악을 발견하는 탐색기',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Color(0xFFA1A1AA), fontSize: 14),
                            ),
                            const SizedBox(height: 26),
                            Container(
                              decoration: BoxDecoration(
                                gradient: const LinearGradient(
                                  colors: [Color(0xFF1A1A25), Color(0xFF14141D)],
                                  begin: Alignment.topLeft,
                                  end: Alignment.bottomRight,
                                ),
                                borderRadius: BorderRadius.circular(18),
                                border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
                              ),
                              padding: const EdgeInsets.symmetric(horizontal: 16),
                              child: TextField(
                                controller: _controller,
                                textInputAction: TextInputAction.search,
                                onSubmitted: (_) => _startMockSearch(),
                                textAlign: TextAlign.center,
                                style: const TextStyle(color: Color(0xFFF4F4F5), fontSize: 15),
                                decoration: const InputDecoration(
                                  hintText: '키워드로 음악을 탐색해 보세요',
                                  hintStyle: TextStyle(color: Color(0xFFA1A1AA)),
                                  border: InputBorder.none,
                                  icon: Icon(Icons.search_rounded, color: Color(0xFF94A3B8)),
                                ),
                              ),
                            ),
                            const SizedBox(height: 16),
                            Wrap(
                              alignment: WrapAlignment.center,
                              spacing: 8,
                              runSpacing: 8,
                              children: suggestions
                                  .map(
                                    (item) => ActionChip(
                                      backgroundColor: const Color(0xFF1A1A25),
                                      side: BorderSide(color: Colors.white.withValues(alpha: 0.12)),
                                      label: Text(item, style: const TextStyle(color: Color(0xFFE4E4E7), fontSize: 12)),
                                      onPressed: () => setState(() => _appendKeyword(item)),
                                    ),
                                  )
                                  .toList(),
                            ),
                            const SizedBox(height: 26),
                            SizedBox(
                              width: math.min(maxContentWidth * 0.52, 220),
                              child: FilledButton(
                                onPressed: _startMockSearch,
                                style: FilledButton.styleFrom(
                                  backgroundColor: const Color(0xFF0F766E),
                                  foregroundColor: Colors.white,
                                  elevation: 0,
                                  padding: const EdgeInsets.symmetric(vertical: 16),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                                ),
                                child: const Text('탐색 시작', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class VinylLoadingDialog extends StatefulWidget {
  const VinylLoadingDialog({super.key});

  @override
  State<VinylLoadingDialog> createState() => _VinylLoadingDialogState();
}

class _VinylLoadingDialogState extends State<VinylLoadingDialog> with TickerProviderStateMixin {
  late final AnimationController _discController;
  late final AnimationController _headController;
  Timer? _lineTimer;
  int _lineIndex = 0;
  bool _isDone = false;

  static const _lines = [
    '스포티파이 탐색 중...',
    '당신의 취향 바깥을 여행하는 중...',
    '숨겨진 트랙을 찾고 있어요...',
    'Side-B 감성 매칭 중...',
  ];

  @override
  void initState() {
    super.initState();
    _discController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1700))
      ..repeat();
    _headController = AnimationController(vsync: this, duration: const Duration(milliseconds: 900));

    _lineTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      if (!mounted || _isDone) {
        return;
      }
      setState(() {
        _lineIndex = (_lineIndex + 1) % _lines.length;
      });
    });

    Future<void>.delayed(const Duration(seconds: 5), () async {
      if (!mounted) {
        return;
      }
      _isDone = true;
      await _headController.forward();
      await Future<void>.delayed(const Duration(milliseconds: 250));
      _discController.stop();
      await Future<void>.delayed(const Duration(milliseconds: 300));
      if (mounted) {
        Navigator.of(context).pop();
      }
    });
  }

  @override
  void dispose() {
    _lineTimer?.cancel();
    _discController.dispose();
    _headController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: const Color(0xFF111119),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
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
                            border: Border.all(color: const Color(0xFF4B5563).withValues(alpha: 0.3), width: 1),
                            boxShadow: const [
                              BoxShadow(color: Color(0x66000000), blurRadius: 12, offset: Offset(0, 6)),
                            ],
                          ),
                        ),
                        Container(
                          width: 78,
                          height: 78,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white.withValues(alpha: 0.09), width: 2),
                          ),
                        ),
                        Container(
                          width: 52,
                          height: 52,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white.withValues(alpha: 0.08), width: 2),
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
                  AnimatedBuilder(
                    animation: _headController,
                    builder: (_, __) {
                      // 0.0: 레코드 위 안착 상태 -> 1.0: 바깥으로 들려 이동한 상태
                      final armAngle = lerpDouble(2.55, 3.35, _headController.value)!;
                      return Positioned(
                        right: 22,
                        top: 16,
                        child: Transform.rotate(
                          angle: armAngle,
                          alignment: Alignment.centerLeft,
                          child: SizedBox(
                            width: 62,
                            height: 18,
                            child: Stack(
                              clipBehavior: Clip.none,
                              alignment: Alignment.centerLeft,
                              children: [
                                Container(
                                  width: 52,
                                  height: 4,
                                  margin: const EdgeInsets.only(left: 2),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF9CA3AF),
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                ),
                                Positioned(
                                  right: 2,
                                  child: Container(
                                    width: 10,
                                    height: 10,
                                    decoration: const BoxDecoration(
                                      color: Color(0xFFF472B6),
                                      shape: BoxShape.circle,
                                    ),
                                  ),
                                ),
                                Positioned(
                                  right: -2,
                                  top: 7,
                                  child: Container(
                                    width: 8,
                                    height: 4,
                                    decoration: BoxDecoration(
                                      color: const Color(0xFFE5E7EB),
                                      borderRadius: BorderRadius.circular(2),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                  Positioned(
                    right: 50,
                    top: 14,
                    child: Container(
                      width: 10,
                      height: 10,
                      decoration: const BoxDecoration(color: Color(0xFF6B7280), shape: BoxShape.circle),
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
                  const Text('분석 중', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 12),
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 300),
                    child: Text(
                      _lines[_lineIndex],
                      key: ValueKey(_lineIndex),
                      style: const TextStyle(color: Color(0xFFA1A1AA), height: 1.4, fontSize: 13),
                    ),
                  ),
                  const SizedBox(height: 12),
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
    );
  }
}

class _GlowOrb extends StatelessWidget {
  const _GlowOrb({required this.size, required this.color});

  final double size;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [color, color.withValues(alpha: 0)],
            stops: const [0.15, 1],
          ),
        ),
      ),
    );
  }
}
