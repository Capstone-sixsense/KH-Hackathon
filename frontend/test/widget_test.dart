// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';

import 'package:khuthon/main.dart';

void main() {
  testWidgets('Side-B search screen smoke test', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const SideBApp());

    expect(find.text('Side-B'), findsOneWidget);
    expect(find.text('들리지 않던 쪽으로, 취향의 이면을 넘기다'), findsOneWidget);
  });
}
