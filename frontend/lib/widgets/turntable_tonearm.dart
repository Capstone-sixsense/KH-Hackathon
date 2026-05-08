import 'package:flutter/material.dart';

class TurntableTonearm extends StatelessWidget {
  const TurntableTonearm({
    super.key,
    required this.size,
    this.accent = const Color(0xFFF472B6),
    this.opacity = 1,
    this.rotation = 0,
  });

  final double size;
  final Color accent;
  final double opacity;
  final double rotation;

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: rotation,
      alignment: Alignment.topRight,
      child: Opacity(
        opacity: opacity,
        child: SizedBox(
          width: size,
          height: size * 0.74,
          child: CustomPaint(painter: _TurntableTonearmPainter(accent: accent)),
        ),
      ),
    );
  }
}

class _TurntableTonearmPainter extends CustomPainter {
  const _TurntableTonearmPainter({required this.accent});

  final Color accent;

  @override
  void paint(Canvas canvas, Size size) {
    final pivot = Offset(size.width * 0.78, size.height * 0.18);
    final elbow = Offset(size.width * 0.53, size.height * 0.34);
    final stylus = Offset(size.width * 0.17, size.height * 0.78);

    final shadowPaint = Paint()
      ..color = Colors.black.withValues(alpha: 0.34)
      ..strokeWidth = size.width * 0.055
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    final armPaint = Paint()
      ..shader = const LinearGradient(
        colors: [Color(0xFFF4F4F5), Color(0xFF9CA3AF), Color(0xFFE5E7EB)],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height))
      ..strokeWidth = size.width * 0.035
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    final highlightPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.42)
      ..strokeWidth = size.width * 0.01
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    final path = Path()
      ..moveTo(pivot.dx, pivot.dy)
      ..quadraticBezierTo(elbow.dx, elbow.dy, stylus.dx, stylus.dy);
    canvas.drawPath(path.shift(const Offset(0, 5)), shadowPaint);
    canvas.drawPath(path, armPaint);
    canvas.drawPath(
      Path()
        ..moveTo(pivot.dx - size.width * 0.02, pivot.dy - size.height * 0.02)
        ..quadraticBezierTo(
          elbow.dx - size.width * 0.01,
          elbow.dy - size.height * 0.02,
          stylus.dx + size.width * 0.02,
          stylus.dy - size.height * 0.03,
        ),
      highlightPaint,
    );

    final pivotOuterPaint = Paint()..color = const Color(0xFF1F2937);
    final pivotInnerPaint = Paint()..color = const Color(0xFF6B7280);
    final pivotAccentPaint = Paint()..color = accent;
    canvas.drawCircle(pivot, size.width * 0.12, pivotOuterPaint);
    canvas.drawCircle(pivot, size.width * 0.076, pivotInnerPaint);
    canvas.drawCircle(pivot, size.width * 0.032, pivotAccentPaint);

    final headShellRect = RRect.fromRectAndRadius(
      Rect.fromCenter(
        center: stylus.translate(size.width * 0.02, -size.height * 0.01),
        width: size.width * 0.18,
        height: size.height * 0.09,
      ),
      Radius.circular(size.width * 0.02),
    );
    canvas.save();
    canvas.translate(stylus.dx, stylus.dy);
    canvas.rotate(-0.28);
    canvas.translate(-stylus.dx, -stylus.dy);
    canvas.drawRRect(headShellRect, Paint()..color = const Color(0xFFE5E7EB));
    canvas.drawCircle(
      stylus.translate(size.width * 0.08, size.height * 0.035),
      size.width * 0.027,
      Paint()..color = accent,
    );
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _TurntableTonearmPainter oldDelegate) {
    return oldDelegate.accent != accent;
  }
}
