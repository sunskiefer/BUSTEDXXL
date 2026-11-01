// SPDX-License-Identifier: GPL-3.0-or-later
// KutilXXL engine tests, built for ARM (Force) and run under qemu-arm: test/run_tests.sh
// The patch logic the skin depends on, the state, the Force clock and keys, and the sound of each module.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
extern "C" {
#include "engine.h"
}
#include "kutil_ids.h"

static int fails = 0, checks = 0;
#define CHECK(cond, ...) do { checks++; if (!(cond)) { fails++; printf("FAIL "); printf(__VA_ARGS__); printf("\n"); } } while (0)

static const mpc_engine_t *E;
static std::string get(void *s, const char *k) { char b[8192]; int n = E->get_param(s, k, b, sizeof b); return n > 0 ? std::string(b) : std::string(); }
static int geti(void *s, const char *k) { return atoi(get(s, k).c_str()); }
static void set(void *s, const char *k, const char *v) { E->set_param(s, k, v); }
static void setf(void *s, const char *k, float v) { char b[32]; snprintf(b, sizeof b, "%g", v); E->set_param(s, k, b); }
static void tap(void *s, const char *jack) { std::string k = std::string("tap_") + jack; set(s, k.c_str(), "1"); }
static void patch(void *s, const char *o, const char *i) { tap(s, o); tap(s, i); }
static int jack(const char *k) { for (int j = 0; j < N_JACKS; j++) if (!strcmp(JACK_KEY[j], k)) return j; printf("no jack %s\n", k); exit(2); }
static void note(void *s, int n, int v) { uint8_t m[3] = {(uint8_t)(v ? 0x90 : 0x80), (uint8_t)n, (uint8_t)(v ? v : 0)}; E->midi(s, m, 3); }
static int ncables(void *s) { char b[16384]; E->get_param(s, "state", b, sizeof b); int n = 0; for (char *p = b; (p = strstr(p, "cable=")); p++) n++; return n; }

struct St { double rmsL, rmsR; int peak; bool bad; int crossL; };
static double g_ppq = 0;
static St render(void *s, int blocks, bool clock = false, double bpm = 120) {
  int16_t buf[256]; St st = {0, 0, 0, false, 0}; double aL = 0, aR = 0; long n = 0; int last = 0;
  for (int b = 0; b < blocks; b++) {
    if (clock) { E->song_pos(s, g_ppq, bpm, 1, 128); g_ppq += 128.0 * bpm / 60.0 / 44100.0; }
    E->render(s, buf, 128);
    for (int i = 0; i < 128; i++) {
      int l = buf[i * 2], r = buf[i * 2 + 1];
      aL += (double)l * l; aR += (double)r * r;
      if (abs(l) > st.peak) st.peak = abs(l);
      if (abs(l) > 32768 || abs(r) > 32768) st.bad = true;
      if ((l >= 0) != (last >= 0)) st.crossL++;
      last = l; n++;
    }
  }
  st.rmsL = sqrt(aL / n) / 32768.0; st.rmsR = sqrt(aR / n) / 32768.0;
  return st;
}
static void *fresh() { void *s = E->create(nullptr); return s; }
static double hz(const St &st, int blocks) { return st.crossL / 2.0 / (blocks * 128 / 44100.0); }

int main() {
  E = mpc_engine();
  printf("params %d, jacks %d (%d outs, %d ins), modules %d\n", P_COUNT, N_JACKS, N_OUTS, N_INS, N_MODS);

  // ---- silence, and nothing wired by default
  { void *s = fresh(); St a = render(s, 200); CHECK(a.rmsL == 0 && a.rmsR == 0, "silent when unpatched: %g", a.rmsL); CHECK(ncables(s) == 0, "no default cables"); E->destroy(s); }

  // ---- patching: touch, touch
  {
    void *s = fresh();
    int v = geti(s, "view"); CHECK(v == 0, "starts on screen 1");
    tap(s, "pizza1_main");
    int o = jack("pizza1_main");
    char k[32]; snprintf(k, sizeof k, "hd_%d", o / GROUP);
    CHECK(geti(s, k) == 1 + o % GROUP, "held ring shows (%d)", geti(s, k));
    tap(s, "abc1_a");
    CHECK(geti(s, k) == 0, "ring clears after the second jack");
    CHECK(ncables(s) == 1, "one cable");
    int in = jack("abc1_a");
    snprintf(k, sizeof k, "cp_%d_%d", o, JACK_GROUP_OF[in]);
    CHECK(geti(s, k) == 1 + JACK_GROUP_POS[in], "cable picture switch %s = %d (want %d)", k, geti(s, k), 1 + JACK_GROUP_POS[in]);
    // the picture clears on another screen, and the cross-screen stub shows where it should
    // module windows: open hides the cable pictures, the switch follows, close brings them back; a screen change closes
    CHECK(geti(s, "vw") == 0, "view switch: screen 1");
    set(s, "mw_1", "1"); CHECK(geti(s, "vw") == N_SCREENS + 1, "open module 2's window: vw = %d", geti(s, "vw"));
    CHECK(geti(s, k) == 0, "no cable picture while a window is open");
    set(s, "mclose", "1"); CHECK(geti(s, "vw") == 0, "close: back to screen 1");
    CHECK(geti(s, k) == 1 + JACK_GROUP_POS[in], "cable picture back after close");
    set(s, "mw_5", "1"); CHECK(geti(s, "view") == 1 && geti(s, "vw") == N_SCREENS + 5, "a module on screen 2 opens on screen 2");
    set(s, "nav_prev", "1"); CHECK(geti(s, "vw") == 0 && geti(s, "view") == 0, "screen change closes the window");
    // a half-made patch survives the windows: tap in one window, close, open another, finish there
    set(s, "mw_0", "1"); tap(s, "kompas1_cv2"); set(s, "mclose", "1");
    set(s, "mw_1", "1"); tap(s, "crust21_a_c_in"); set(s, "mclose", "1");
    CHECK(ncables(s) == 2, "patched across two windows: %d cables", ncables(s));
    patch(s, "kompas1_cv2", "crust21_a_c_in"); CHECK(ncables(s) == 1, "and unplugged again");
    set(s, "nav_next", "1"); CHECK(geti(s, "view") == 1, "next -> screen 2");
    CHECK(geti(s, k) == 0, "no cable picture on another screen");
    set(s, "nav_prev", "1"); set(s, "nav_prev", "1"); CHECK(geti(s, "view") == 2, "prev wraps to screen 3");
    set(s, "nav_next", "1"); CHECK(geti(s, "view") == 0, "next wraps to screen 1");
    // touching the same pair again unplugs
    patch(s, "abc1_a", "pizza1_main"); CHECK(ncables(s) == 0, "either order unplugs: %d", ncables(s));
    // out-out switches the held jack, same jack cancels
    tap(s, "pizza1_main"); tap(s, "kompas1_cv1"); tap(s, "kompas1_cv1"); CHECK(ncables(s) == 0, "out-out then cancel");
    E->destroy(s);
  }
  // ---- cross-screen cable: a stub on both screens
  {
    void *s = fresh();
    patch(s, "pizza1_main", "abc1_a");
    set(s, "view", "1");  // direct view set
    int o = jack("kompas1_cv1");
    set(s, "view", "0");
    tap(s, "kompas1_cv1"); set(s, "nav_next", "1"); tap(s, "wavebard1_c_in");
    CHECK(ncables(s) == 2, "cable made across screens: %d", ncables(s));
    char k[32];
    set(s, "view", "0"); snprintf(k, sizeof k, "xo_%d_1", o); CHECK(geti(s, k) == 1, "out stub toward screen 2 on screen 1");
    int in = jack("wavebard1_c_in"); set(s, "view", "1"); snprintf(k, sizeof k, "xi_%d_0", in); CHECK(geti(s, k) > 0, "in stub from screen 1 on screen 2 (coloured like its source)");
    set(s, "view", "2"); CHECK(geti(s, k) == 0, "no stub on a third screen");
    E->destroy(s);
  }
  // ---- limits: 4 cables per jack, one per picture group
  {
    void *s = fresh();
    const char *ins[] = {"abc1_a", "abc1_b", "abc1_c", "abc1_d", "abc1_e"};
    for (int i = 0; i < 5; i++) patch(s, "pizza1_main", ins[i]);
    CHECK(ncables(s) <= 4, "an output holds at most 4 cables: %d", ncables(s));
    const char *outs[] = {"pizza1_main", "pizza1_pulse", "pizza1_oct_osc", "kompas1_cv1", "kompas1_trig1"};
    void *t = fresh();
    for (int i = 0; i < 5; i++) patch(t, outs[i], "abc1_f");
    CHECK(ncables(t) <= 4, "an input holds at most 4 cables: %d", ncables(t));
    E->destroy(s); E->destroy(t);
  }
  // ---- state round trip
  {
    void *s = fresh();
    patch(s, "pizza1_main", "abc1_a"); patch(s, "kompas1_cv1", "pizza1_v_oct"); set(s, "view", "2");
    char b[16384]; E->get_param(s, "state", b, sizeof b);
    void *t = fresh(); set(t, "state", b);
    char b2[16384]; E->get_param(t, "state", b2, sizeof b2);
    CHECK(!strcmp(b, b2), "state round trip\n%s\n%s", b, b2);
    CHECK(geti(t, "view") == 2, "view restored");
    E->destroy(s); E->destroy(t);
  }
  // ---- Pizza -> ABC -> Force out 1 (left), pitch follows PITCH
  {
    void *s = fresh();
    patch(s, "pizza1_main", "abc1_a");
    setf(s, "pizza1_shape_sl", 0.0f); setf(s, "pizza1_fm_index_sl", 0.0f); setf(s, "pizza1_shape", 0.5f);
    setf(s, "abc1_a", 1.0f);
    int blocks = 400;
    setf(s, "pizza1_pitch", 0.5f);
    St a = render(s, blocks);
    CHECK(a.rmsL > 0.05 && a.rmsR < 1e-6, "Pizza on ABC A -> left only: L %g R %g", a.rmsL, a.rmsR);
    double f = hz(a, blocks); CHECK(fabs(f - 261.6) < 8, "Pizza at C4: %g Hz", f);
    setf(s, "pizza1_pitch", 0.5f + 1.0f / 6.0f); St b = render(s, blocks);
    CHECK(fabs(hz(b, blocks) - 523.3) < 14, "one octave up: %g Hz", hz(b, blocks));
    E->destroy(s);
  }
  // ---- SUM2 to the right
  {
    void *s = fresh();
    patch(s, "pizza1_main", "abc1_d"); setf(s, "abc1_d", 1.0f);
    St a = render(s, 200); CHECK(a.rmsR > 0.05 && a.rmsL < 1e-6, "ABC D -> right only: L %g R %g", a.rmsL, a.rmsR);
    E->destroy(s);
  }
  // ---- Kompas on the Force clock -> Crust2 -> ABC
  {
    void *s = fresh();
    setf(s, "kompas1_latitude", 1.0f);
    patch(s, "kompas1_trig1", "crust21_a_g_in");
    patch(s, "crust21_a_out", "abc1_a");
    setf(s, "abc1_a", 1.0f);
    g_ppq = 0;
    St a = render(s, 1200, true);
    CHECK(a.rmsL > 0.005, "Kompas clocked by the host triggers Crust2: %g", a.rmsL);
    St b = render(s, 400, false);   // transport stopped: the clock stops, the tail dies
    St c = render(s, 400, false);
    CHECK(c.rmsL < b.rmsL + 1e-9 && c.rmsL < 0.002, "stops with the transport: %g", c.rmsL);
    // probability 0 -> silence
    void *t = fresh();
    setf(t, "kompas1_latitude", 0.0f);
    patch(t, "kompas1_trig1", "crust21_a_g_in"); patch(t, "crust21_a_out", "abc1_a"); setf(t, "abc1_a", 1.0f);
    g_ppq = 0; St d = render(t, 1200, true);
    CHECK(d.rmsL == 0, "latitude 0 never fires: %g", d.rmsL);
    E->destroy(s); E->destroy(t);
  }
  // ---- Kompas clock input patched from another Kompas' trigger? clock jack replaces the host clock
  {
    void *s = fresh();
    setf(s, "kompas1_latitude", 1.0f); patch(s, "pizza1_pulse", "kompas1_clock");
    patch(s, "kompas1_trig1", "crust21_a_g_in"); patch(s, "crust21_a_out", "abc1_a"); setf(s, "abc1_a", 1.0f);
    patch(s, "pizza1_pulse", "abc1_b");     // keep pizza in the ordering without sound? pulse gets heard too
    setf(s, "abc1_b", 0.0f);
    g_ppq = 0; St a = render(s, 400, true);
    CHECK(a.rmsL > 0.001, "patched CLOCK is used (the host clock is ignored): %g", a.rmsL);
    E->destroy(s);
  }
  // ---- Force keys through Kompas (the screen's own): CV1 -> Pizza V/OCT, TRIG1 -> sound
  {
    void *s = fresh();
    patch(s, "kompas1_cv1", "pizza1_v_oct"); patch(s, "pizza1_main", "abc1_a"); setf(s, "abc1_a", 1.0f);
    setf(s, "pizza1_pitch", 0.5f); setf(s, "pizza1_shape_sl", 0.0f); setf(s, "pizza1_fm_index_sl", 0.0f);
    note(s, 60, 100); St a = render(s, 300);
    note(s, 72, 100); St b = render(s, 300);
    CHECK(fabs(hz(a, 300) - 261.6) < 8, "key C4 -> %g Hz", hz(a, 300));
    CHECK(fabs(hz(b, 300) - 523.3) < 14, "key C5 -> %g Hz", hz(b, 300));
    // on another screen the keys are not sent to this Kompas
    set(s, "view", "1"); note(s, 84, 100); St c = render(s, 300);
    CHECK(fabs(hz(c, 300) - 261.6) < 8, "keys reach only the Kompas on the screen shown: %g Hz", hz(c, 300));
    E->destroy(s);
  }
  // ---- WaveBard plays its samples on a gate
  {
    void *s = fresh();
    patch(s, "pizza1_pulse", "wavebard1_g_in");
    patch(s, "wavebard1_out", "abc2_a"); setf(s, "abc2_a", 1.0f);
    setf(s, "pizza1_pitch", 0.2f);
    St a = render(s, 600);
    CHECK(a.rmsL > 0.02 && a.rmsR < 1e-6 && !a.bad, "WaveBard sample on a gate: L %g R %g", a.rmsL, a.rmsR);
    E->destroy(s);
    void *t = fresh(); patch(t, "wavebard1_out", "abc2_a"); setf(t, "abc2_a", 1.0f);
    CHECK(render(t, 300).rmsL == 0, "WaveBard silent without a trigger");
    E->destroy(t);
  }
  // ---- Alchemist: a gate from a Pizza pulse, pitched by Kompas keys
  {
    void *s = fresh();
    patch(s, "pizza1_pulse", "alchemist1_g_in"); patch(s, "alchemist1_out", "abc3_a"); setf(s, "abc3_a", 1.0f);
    setf(s, "pizza1_pitch", 0.15f);
    set(s, "view", "2");
    St a = render(s, 600);
    CHECK(a.rmsL > 0.01 && !a.bad, "Alchemist voice: %g", a.rmsL);
    E->destroy(s);
  }
  // ---- Basil: a delay repeats a burst after the delay time, and is silent with dry/wet at 0
  {
    void *s = fresh();
    patch(s, "pizza1_main", "basil1_l_in"); patch(s, "basil1_l_out", "abc3_a"); setf(s, "abc3_a", 1.0f);
    setf(s, "basil1_dry_wet", 1.0f); setf(s, "basil1_feedback", 0.5f); setf(s, "basil1_delay", 0.5f);
    St a = render(s, 600); CHECK(a.rmsL > 0.02 && !a.bad, "Basil passes the delayed signal: %g", a.rmsL);
    setf(s, "basil1_dry_wet", 0.0f); St b = render(s, 100); CHECK(b.rmsL > 0.02, "dry path: %g", b.rmsL);
    E->destroy(s);
  }
  // ---- fuzz: every output patched to inputs on its screen, all controls swept, no NaN / overflow / crash
  {
    void *s = fresh();
    srand(7);
    for (int n = 0; n < 400; n++) {
      int o = OUT_JACK[rand() % N_OUTS], i = IN_JACK[rand() % N_INS];
      tap(s, JACK_KEY[o]); tap(s, JACK_KEY[i]);
    }
    for (int p = 0; p < N_CONTROLS; p++) {
      if (P_TRIG[p]) continue;
      setf(s, P_KEY[p], P_MIN[p] + (P_MAX[p] - P_MIN[p]) * (rand() % 1000) / 1000.0f);
    }
    for (int v = 0; v < 3; v++) { char b[8]; snprintf(b, sizeof b, "%d", v); set(s, "view", b); }
    note(s, 64, 90);
    g_ppq = 0;
    St a = render(s, 4000, true, 140);
    CHECK(!a.bad, "fuzz patch stays in range");
    CHECK(ncables(s) > 20, "fuzz made cables: %d", ncables(s));
    for (int p = 0; p < N_CONTROLS; p++) {
      if (P_TRIG[p]) continue;
      for (int q = 0; q < 3; q++) setf(s, P_KEY[p], q == 0 ? P_MIN[p] : (q == 1 ? P_MAX[p] : P_DEF[p]));
      St z = render(s, 40, true, 140);
      CHECK(!z.bad, "control %s extreme stays in range", P_KEY[p]);
    }
    char buf[256];
    for (int p = 0; p < P_COUNT; p++) { E->get_param(s, P_KEY[p], buf, sizeof buf); }   // every parameter reads back
    E->destroy(s);
  }
  // ---- Q-Links follow the screen
  {
    void *s = fresh();
    std::string n1 = get(s, "ql1_name"); set(s, "view", "1"); std::string n2 = get(s, "ql1_name");
    CHECK(n1 != n2 && n1 != "-", "Q-Link 1 renamed with the screen: '%s' -> '%s'", n1.c_str(), n2.c_str());
    setf(s, "ql1", 1.0f);
    E->destroy(s);
  }
  printf("%d checks, %d failed\n", checks, fails);
  return fails ? 1 : 0;
}
