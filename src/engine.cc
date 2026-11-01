// SPDX-License-Identifier: GPL-3.0-or-later
// KutilXXL engine: twelve modules (three screens of a Bastl-style groovebox), a patch matrix between their jacks, the
// Force's clock and keys, and the ABC mixers' sums to the Force's audio output 1/2.
//
// Signals are volts, as on a modular: audio +-5, CV +-5 (pitch 1 V/oct, 0 V = C4), gates and triggers 0 / 5.
// Modules run one sample at a time in screen order; an input reads the sum of the outputs patched to it as they stand
// (a module later in the order than its source sees this sample's value, an earlier one the previous sample's).
// Nothing is wired by default: an unpatched input reads 0.
// The modules other than the open-source Bastl designs are this project's own readings of what such a module does:
// docs/MODULES.md says what each jack and control does here.
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <new>

extern "C" {
#include "engine.h"
}
#include "kutil_ids.h"

// Bastl Instruments' Kastle 2 DSP (MIT, see src/bastl/LICENSE-kastle2-MIT): sample player, stereo delay, FM and multi
// oscillators, envelope, LFO, filters, quantizer
#include "common/dsp/control/AdsrEnv.hpp"
#include "common/dsp/control/Lfo.hpp"
#include "common/dsp/effects/StereoDelay.hpp"
#include "common/dsp/filters/Svf.hpp"
#include "common/dsp/sampling/SamplePlayer.hpp"
#include "common/dsp/synthesis/Fm2.hpp"
#include "common/dsp/synthesis/MultiOscillator.hpp"
#include "common/dsp/utility/Quantizer.hpp"
#include "apps/WaveBardMaps.hpp"
using namespace kastle2;

namespace {

const float SR = 44100.0f;   // kastle2::SAMPLE_RATE is the same here
const float PI2 = 6.28318530718f;

inline float clampf(float x, float a, float b) { return x < a ? a : (x > b ? b : x); }
inline float flush(float x) { return (x > -1e-20f && x < 1e-20f) ? 0.0f : x; }

struct Rng {
  uint32_t s = 2463534242u;
  uint32_t next() { s ^= s << 13; s ^= s >> 17; s ^= s << 5; return s; }
  float uni() { return (next() >> 8) * (1.0f / 16777216.0f); }      // 0..1
  float bi() { return uni() * 2.0f - 1.0f; }
};

struct Edge {   // rising edge of a gate (threshold 1 V)
  bool hi = false;
  bool up(float v) { bool h = v > 1.0f; bool r = h && !hi; hi = h; return r; }
};

struct Eng;

// ---- Wave Bard's samples ------------------------------------------------------------------------------------------------
// The real Wave Bard format (kastle2 apps/WaveBard/WAVE_BARD_FORMAT.md): if SAMPLES.bin sits in the plugin's folder (or the
// folder the host starts in) it is loaded as Bastl's firmware does -- banks, samples, the file's own scales. Bastl's factory
// SAMPLES.bin is "All rights reserved" and is not shipped here. Without a file, a small bank of synthesised sounds stands in
// (8 banks x 8 sounds, mono, 16-bit): drums, plucks, pads, bells, textures.
const int MAX_BANKS = 32, MAX_PER_BANK = 32;
struct SampleRef { const int16_t *data; size_t len; int ch; };
struct Bank {
  int16_t *pool = nullptr;
  SampleRef s[MAX_BANKS][MAX_PER_BANK];
  int nbanks = 0, nsamples = 0, nscales = 0;
  uint32_t scales[32];
  float rate = 44100.0f;
  bool from_file = false;
  int refs = 0;
};
Bank *g_bank = nullptr;

const uint32_t DEFAULT_SCALES[7] = {0b000010001001, 0b010010101001, 0b010110101101, 0b111111111111, 0b101010110101, 0b001010010101, 0b000010010001};

bool load_wave_bard(Bank *b, const char *path) {
  FILE *f = fopen(path, "rb");
  if (!f) return false;
  fseek(f, 0, SEEK_END);
  long sz = ftell(f);
  fseek(f, 0, SEEK_SET);
  if (sz < 64 || sz > 16 * 1024 * 1024) { fclose(f); return false; }
  uint8_t *d = (uint8_t *)malloc(sz);
  if (!d || fread(d, 1, sz, f) != (size_t)sz) { free(d); fclose(f); return false; }
  fclose(f);
  auto u32 = [&](long o) { uint32_t v; memcpy(&v, d + o, 4); return v; };
  bool ok = memcmp(d, "k2wb", 4) == 0 && u32(4) <= (uint32_t)sz && memcmp(d + u32(4) - 4, "ahoj", 4) == 0 && d[16] == 16;
  if (!ok) { free(d); return false; }
  int nb = d[17], ns = d[18], nsc = d[19], nr = d[20];
  if (nb < 1 || nb > MAX_BANKS || ns < 1 || ns > MAX_PER_BANK || nsc < 1 || nsc > 32 || nr < 1 || nr > 64) { free(d); return false; }
  long o = 20;
  for (int i = 0; i < nsc; i++, o += 4) b->scales[i] = u32(o);
  o += 4L * nr;                                   // rhythms: the sequencer's, not used here
  int16_t *pool = (int16_t *)malloc((size_t)sz);  // sample data, copied aligned
  if (!pool) { free(d); return false; }
  size_t used = 0;
  for (int bk = 0; bk < nb; bk++) {
    o += 12;                                       // bank header
    for (int k = 0; k < ns; k++) {
      if (o + 16 > sz) { free(pool); free(d); return false; }
      uint32_t bytes = u32(o);
      int ch = d[o + 4] == 2 ? 2 : 1;
      o += 16;
      if (bytes > (uint32_t)(sz - o)) { free(pool); free(d); return false; }
      memcpy((uint8_t *)pool + used * 2, d + o, bytes);
      b->s[bk][k].data = pool + used;
      b->s[bk][k].len = bytes / 2 / ch;
      b->s[bk][k].ch = ch;
      used += bytes / 2;
      o += bytes;
    }
  }
  b->pool = pool; b->nbanks = nb; b->nsamples = ns; b->nscales = nsc;
  b->rate = (float)u32(8);
  b->from_file = true;
  free(d);
  return true;
}

void synth_bank(Bank *b) {
  const int B = 8, K = 8, SL = 22050;
  b->pool = (int16_t *)calloc((size_t)B * K * SL, sizeof(int16_t));
  if (!b->pool) return;
  Rng r;
  for (int bk = 0; bk < B; bk++) for (int k = 0; k < K; k++) {
    int16_t *o = b->pool + ((size_t)bk * K + k) * SL;
    float t = k / 7.0f, ph = 0, lp = 0, hp = 0, ks[1024];
    int kl = 60 + k * 40;
    for (int i = 0; i < kl && i < 1024; i++) ks[i] = r.bi();
    int kp = 0;
    for (int i = 0; i < SL; i++) {
      float x = i / SR, y = 0;
      switch (bk) {
        case 0: { float f = 40 + 30 * t + 220 * expf(-x * (30 - 15 * t)); ph += f / SR; y = sinf(PI2 * ph) * expf(-x * (5 + 6 * (1 - t))); break; }
        case 1: { float n = r.bi(); lp += 0.4f * (n - lp); float tone = sinf(PI2 * (170 + 60 * t) * x); y = (0.6f * lp + 0.5f * tone * expf(-x * 30)) * expf(-x * (14 - 6 * t)); break; }
        case 2: { float n = r.bi(); hp = 0.8f * (hp + n - lp); lp = n; y = hp * expf(-x * (40 - 28 * t)); break; }
        case 3: { int n = kl < 1024 ? kl : 1024; float v = ks[kp]; ks[kp] = 0.5f * (ks[kp] + ks[(kp + 1) % n]) * 0.996f; kp = (kp + 1) % n; y = v * expf(-x * 2.0f); break; }
        case 4: { for (int h = 1; h <= 4; h++) y += sinf(PI2 * 110 * (1 + t) * h * x) / h; y *= 0.4f * sinf(3.14159f * clampf(x / 0.5f, 0, 1)); break; }
        case 5: { float f0 = 130 + 40 * t; ph += f0 / SR; float s = ph - floorf(ph); float saw = 2 * s - 1; float f1 = 500 + 900 * t; lp += (sinf(PI2 * f1 * x) * saw - lp) * 0.3f; y = (0.6f * saw * sinf(PI2 * f1 * x * 0.5f) + lp) * 0.5f * sinf(3.14159f * clampf(x / 0.45f, 0, 1)); break; }
        case 6: { float fc = 200 * (1 + 2 * t); y = sinf(PI2 * fc * x + 3 * sinf(PI2 * fc * 1.41f * x) * expf(-x * 4)) * expf(-x * (3 + 3 * t)); break; }
        default: { float n = r.bi(); lp += (0.02f + 0.3f * t) * (n - lp); y = lp * 2.5f * sinf(3.14159f * clampf(x / 0.5f, 0, 1)) * (0.6f + 0.4f * sinf(PI2 * (3 + 25 * t) * x)); break; }
      }
      if (i >= SL - 128) y *= (SL - 1 - i) / 128.0f;
      o[i] = (int16_t)(clampf(y, -1.0f, 1.0f) * 30000.0f);
    }
    b->s[bk][k].data = o; b->s[bk][k].len = SL; b->s[bk][k].ch = 1;
  }
  b->nbanks = B; b->nsamples = K; b->nscales = 7;
  memcpy(b->scales, DEFAULT_SCALES, sizeof DEFAULT_SCALES);
  b->rate = SR;
}

void acquire_bank(const char *dir) {
  if (g_bank) { g_bank->refs++; return; }
  g_bank = new Bank();
  g_bank->refs = 1;
  char path[512];
  bool ok = false;
  if (dir && *dir) { snprintf(path, sizeof path, "%s/SAMPLES.bin", dir); ok = load_wave_bard(g_bank, path); }
  if (!ok) ok = load_wave_bard(g_bank, "SAMPLES.bin");
  if (!ok) synth_bank(g_bank);
}
void release_bank() {
  if (g_bank && --g_bank->refs == 0) { free(g_bank->pool); delete g_bank; g_bank = nullptr; }
}

// ---- the engine ----------------------------------------------------------------------------------------------------
struct Cable { short o, i; };
const int MAXCAB = 512;

struct Module {
  virtual ~Module() {}
  virtual void tick(Eng &e, int m) = 0;
};

struct Eng {
  float pv[P_COUNT];
  float btn[P_COUNT];                   // pending momentary presses
  int view = 0, held = -1, win = -1;   // win: the module whose jack window is open, or -1
  Cable cab[MAXCAB];
  int ncab = 0;
  unsigned rev = 1;
  char info[160];
  short mj_in[N_MODS][20], mj_out[N_MODS][16];
  float jv[N_JACKS];
  short srcs[N_JACKS][MAX_CABLES];
  unsigned char nsrc[N_JACKS];
  unsigned char nout[N_JACKS];          // cables on an output
  Module *mod[N_MODS];
  // host clock / transport
  double ppq = -1, bpm = 0;
  int playing = 0;
  int clk_left = 0;                      // samples of the current clock pulse left
  int next_edge = -1;                    // sample index in this block of the next 16th, -1 none
  double edge_step = 0;
  bool host_clk = false;
  // Force keys
  int key_note = -1;
  bool key_gate = false;
  bool key_dirty = false;
  Rng rng;

  void init() {
    for (int i = 0; i < P_COUNT; i++) { pv[i] = P_DEF[i]; btn[i] = 0; }
    memset(jv, 0, sizeof jv);
    memset(nsrc, 0, sizeof nsrc);
    memset(nout, 0, sizeof nout);
    memset(mod, 0, sizeof mod);
    for (int m = 0; m < N_MODS; m++) {
      for (int r = 0; r < 20; r++) mj_in[m][r] = -1;
      for (int r = 0; r < 16; r++) mj_out[m][r] = -1;
    }
    for (int j = 0; j < N_JACKS; j++) {
      if (JACK_IS_OUT[j]) mj_out[JACK_MOD[j]][JACK_ROLE[j]] = (short)j;
      else mj_in[JACK_MOD[j]][JACK_ROLE[j]] = (short)j;
    }
    snprintf(info, sizeof info, "Touch a jack, then another jack");
  }
  void bump() { rev++; }

  // ---- patching ---------------------------------------------------------------------------------------------------
  void rebuild() {
    memset(nsrc, 0, sizeof nsrc);
    memset(nout, 0, sizeof nout);
    for (int c = 0; c < ncab; c++) {
      int o = cab[c].o, i = cab[c].i;
      if (nsrc[i] < MAX_CABLES) srcs[i][nsrc[i]++] = (short)o;
      nout[o]++;
    }
  }
  int find_cable(int o, int i) const {
    for (int c = 0; c < ncab; c++) if (cab[c].o == o && cab[c].i == i) return c;
    return -1;
  }
  void remove_at(int c) { cab[c] = cab[--ncab]; }
  // adds o -> i; false when a jack is full. A cable that would share a picture switch with an older one from the same
  // output on the same screen (one input per group) replaces it.
  bool add_cable(int o, int i) {
    if (find_cable(o, i) >= 0) return true;
    if (ncab >= MAXCAB) return false;
    for (int c = 0; c < ncab; c++)
      if (cab[c].o == o && JACK_SCREEN[cab[c].i] == JACK_SCREEN[i] && JACK_SCREEN[i] == JACK_SCREEN[o] &&
          JACK_GROUP_OF[cab[c].i] == JACK_GROUP_OF[i] && JACK_SCREEN[cab[c].i] == JACK_SCREEN[o]) { remove_at(c); break; }
    int cnt_o = 0, cnt_i = 0;
    for (int c = 0; c < ncab; c++) { if (cab[c].o == o) cnt_o++; if (cab[c].i == i) cnt_i++; }
    if (cnt_o >= MAX_CABLES || cnt_i >= MAX_CABLES) return false;
    cab[ncab].o = (short)o; cab[ncab].i = (short)i; ncab++;
    return true;
  }
  void tap(int j) {
    if (held < 0) {
      held = j;
      snprintf(info, sizeof info, "%s: touch another jack", JACK_LABEL[j]);
    } else if (held == j) {
      held = -1;
      snprintf(info, sizeof info, "Cancelled");
    } else if (JACK_IS_OUT[held] == JACK_IS_OUT[j]) {
      held = j;
      snprintf(info, sizeof info, "%s: touch an %s", JACK_LABEL[j], JACK_IS_OUT[j] ? "input" : "output");
    } else {
      int o = JACK_IS_OUT[held] ? held : j, i = JACK_IS_OUT[held] ? j : held;
      int c = find_cable(o, i);
      if (c >= 0) {
        remove_at(c);
        snprintf(info, sizeof info, "Unplugged %s > %s", JACK_LABEL[o], JACK_LABEL[i]);
      } else if (add_cable(o, i)) {
        snprintf(info, sizeof info, "%s > %s", JACK_LABEL[o], JACK_LABEL[i]);
      } else {
        snprintf(info, sizeof info, "Jack full (%d cables)", MAX_CABLES);
      }
      held = -1;
      rebuild();
    }
    bump();
  }
  // vw: the one switch the skin shows everything by: the screen, or N_SCREENS + the open module's window
  void sync_vw() { pv[P_VW] = (float)(win >= 0 ? N_SCREENS + win : view); }
  void open_win(int m) {   // a tap on a module's empty art: its jack window (on that module's screen)
    if (m < 0 || m >= N_MODS) return;
    view = MOD_SCREEN[m];
    pv[P_VIEW] = (float)view;
    win = m;
    sync_vw();
    bump();
  }
  void close_win() {
    if (win < 0) return;
    win = -1;
    sync_vw();
    bump();
  }
  void set_view(int v) {   // a screen change also closes an open window
    v = (int)clampf((float)v, 0, N_SCREENS - 1);
    if (v == view && win < 0) return;
    view = v;
    win = -1;
    pv[P_VIEW] = (float)v;
    sync_vw();
    bump();
  }

  // ---- the picture switches (what the skin shows) ------------------------------------------------------------------
  int vis_value(int k) const {
    int kind = VIS_KIND[k], a = VIS_A[k], b = VIS_B[k];
    if (win >= 0) return 0;      // cables and held rings live on the screens, not in a module's jack window
    if (kind == 0) {            // cp: output a, input group b
      if (JACK_SCREEN[a] != view) return 0;
      for (int c = 0; c < ncab; c++)
        if (cab[c].o == a && JACK_SCREEN[cab[c].i] == view && JACK_GROUP_OF[cab[c].i] == b) return 1 + JACK_GROUP_POS[cab[c].i];
      return 0;
    }
    if (kind == 1) {            // xo: output a to a jack on screen b
      if (JACK_SCREEN[a] != view) return 0;
      for (int c = 0; c < ncab; c++) if (cab[c].o == a && JACK_SCREEN[cab[c].i] == b) return 1;
      return 0;
    }
    if (kind == 2) {            // xi: input a fed from screen b
      if (JACK_SCREEN[a] != view) return 0;
      int r = 0;   // the colour of the newest cable from screen b, so the stub matches the one that left that screen
      for (int c = 0; c < ncab; c++) if (cab[c].i == a && JACK_SCREEN[cab[c].o] == b) r = 1 + JACK_COLOUR[cab[c].o];
      return r;
    }
    if (held < 0 || JACK_SCREEN[held] != view) return 0;   // hd: group a
    return (held / GROUP == a) ? 1 + held % GROUP : 0;
  }

  // ---- reading the patch ---------------------------------------------------------------------------------------------
  inline bool patched_in(int m, int role) const { int j = mj_in[m][role]; return j >= 0 && nsrc[j] > 0; }
  inline float in(int m, int role) const {
    int j = mj_in[m][role];
    if (j < 0) return 0;
    float s = 0;
    for (int k = 0; k < nsrc[j]; k++) s += jv[srcs[j][k]];
    return s;
  }
  inline void out(int m, int role, float v) { int j = mj_out[m][role]; if (j >= 0) jv[j] = v; }
  inline float ctl(int m, int role) const {
    int p = MOD_CTL[m][role];
    return p >= 0 ? pv[p] : CTL_DEF[MOD_TYPE[m]][role];
  }
  inline bool take(int m, int role) {   // a momentary button pressed since the last look
    int p = MOD_CTL[m][role];
    if (p < 0 || btn[p] < 0.5f) return false;
    btn[p] = 0;
    return true;
  }
  inline bool host_edge() const { return host_clk; }

  void set_control(int p, float v) {
    v = clampf(v, P_MIN[p], P_MAX[p]);
    if (P_NOPTS[p] || P_INT[p]) v = roundf(v);
    pv[p] = v;
  }
};

inline float pitch_hz(float v) { return 261.6256f * exp2f(v); }

// ---- Kompas: a probability sequencer --------------------------------------------------------------------------------
// Latitude, altitude and longitude set the chance that clock steps 1, 2 and 3 fire; the other two knobs of each channel
// widen its random pitch. COLLAB: channels 2 and 3 fire only when channel 1 did. STZ-ZOPA: quantise to semitones. FIND
// reseeds. The Force keys (screen's Kompas only) set CV1/TRIG1 while a key is down.
struct Kompas : Module {
  Edge clk, clk2, rst;
  float cv[3] = {0, 0, 0};
  int trig_left[3] = {0, 0, 0};
  Rng r;
  void tick(Eng &e, int m) override {
    float lat = e.ctl(m, KOMPAS_C_LATITUDE), alt = e.ctl(m, KOMPAS_C_ALTITUDE), lon = e.ctl(m, KOMPAS_C_LONGITUDE);
    bool collab = e.ctl(m, KOMPAS_C_COLLAB) > 0.5f, quant = e.ctl(m, KOMPAS_C_STZ_ZOPA) > 0.5f;
    if (e.take(m, KOMPAS_C_FIND)) r.s ^= (uint32_t)(e.rng.next() | 1u);
    bool step = false;
    if (e.patched_in(m, KOMPAS_IN_CLOCK)) step = clk.up(e.in(m, KOMPAS_IN_CLOCK));
    else step = e.host_edge();
    if (e.patched_in(m, KOMPAS_IN_COLLAB)) step = clk2.up(e.in(m, KOMPAS_IN_COLLAB)) || step;
    if (rst.up(e.in(m, KOMPAS_IN_RESET))) r.s = 2463534242u;
    if (step) {
      float k[3] = {lat, alt, lon};
      bool fired0 = false;
      for (int c = 0; c < 3; c++) {
        float p = k[c] * k[c] * (3 - 2 * k[c]);
        bool fire = r.uni() < p;
        if (collab && c > 0 && !fired0) fire = false;
        if (c == 0) fired0 = fire;
        if (fire) {
          float others = (k[(c + 1) % 3] + k[(c + 2) % 3]) * 0.5f;
          float range = 1.0f + 4.0f * others;                // volts, +- half of it
          float v = r.bi() * range * 0.5f;
          if (quant) v = roundf(v * 12.0f) / 12.0f;
          cv[c] = v;
          trig_left[c] = (int)(0.008f * SR);
        }
      }
    }
    bool keys = e.key_dirty ? true : true;
    (void)keys;
    for (int c = 0; c < 3; c++) {
      float t = trig_left[c] > 0 ? 5.0f : 0.0f;
      if (trig_left[c] > 0) trig_left[c]--;
      float v = cv[c];
      if (c == 0 && e.view == MOD_SCREEN[m] && e.key_gate) { v = (e.key_note - 60) / 12.0f; t = 5.0f; }
      else if (c == 0 && e.view == MOD_SCREEN[m] && e.key_note >= 0) v = (e.key_note - 60) / 12.0f;
      e.out(m, KOMPAS_OUT_CV1 + c * 2, v);
      e.out(m, KOMPAS_OUT_TRIG1 + c * 2, t);
    }
  }
};

// ---- helpers over Bastl's fixed-point DSP ------------------------------------------------------------------------------
inline q31_t fq31(float x) { return float_to_q31(clampf(x, -1.0f, 1.0f)); }
inline float q31f(q31_t x) { return q31_to_float(x); }
inline q15_t fq15(float x) { return float_to_q15(clampf(x, -1.0f, 1.0f)); }
inline float q15f(q15_t x) { return q15_to_float(x); }

// An AdsrEnv used as an attack/hold/decay one-shot (Bastl's own envelope), set only when a time changes.
struct Ad {
  AdsrEnv e;
  float a = -1, h = -1, d = -1;
  Ad() { e.Init(SAMPLE_RATE); e.SetNonResetting(AdsrEnv::NonResetting::NONE); e.SetSustainLevel(0); e.SetReleaseTime(0.01f); }
  void set(float at, float ho, float de) {
    if (at != a) { a = at; e.SetAttackTime(at); }
    if (ho != h) { h = ho; e.SetHoldTime(ho); }
    if (de != d) { d = de; e.SetDecayTime(de); }
  }
  float run(bool trig) { if (trig) e.Trigger(); return q31f(e.Process()); }
};

// ---- LFO shared by WaveBard and Alchemist: Bastl's Lfo ------------------------------------------------------------------
struct KLfo {
  Lfo l;
  float sh = 0;
  Edge rst;
  Rng r;
  explicit KLfo(uint32_t seed) { l.Init(SAMPLE_RATE); r.s ^= seed; }
  void run(Eng &e, int m, float freq_knob, float cv, int in_reset, int in_ext, int o_l, int o_a, int o_out, int o_edit, float &sine, float &tri) {
    if (rst.up(e.in(m, in_reset))) l.Reset();
    l.SetFrequency(0.05f * exp2f(freq_knob * 9.0f + clampf(cv, -5, 5) * 0.4f));
    bool last = l.IsLastSample();
    tri = q31f(l.Process());
    if (last) sh = r.bi();
    sine = sinf(tri * 1.5707963f);
    float sq = l.GetSquareOut() ? 1.0f : -1.0f;
    if (e.patched_in(m, in_ext)) { float x = clampf(e.in(m, in_ext) * 0.2f, -1, 1); sine = x; tri = x; sq = x > 0 ? 1.0f : -1.0f; }
    e.out(m, o_l, sine * 5.0f);
    e.out(m, o_a, tri * 5.0f);
    e.out(m, o_out, sq * 5.0f);
    e.out(m, o_edit, sh * 5.0f);
  }
};

// ---- Crust 2: two drum voices (this project's own design on Bastl's oscillators and envelope) ---------------------------
// Each half: G_IN (A also TRIG) triggers it; with nothing on the gate jacks a pulse on CLK_IN does. C_IN (B also PITCH
// V/OCT) pitches it, VELOCITY scales it, LAYER_CTRL adds to LAYER. SAMPLE MOD morphs the body into noise, LENGTH is the
// decay, LAYER balances body against the click, CTRL is the pitch-drop depth, BANK picks the body wave (sine, triangle,
// square, FM), LFO MOD sends the half's own LFO to the pitch. CV-GATE: gate held (on) or one-shot (off).
struct CrustHalf {
  Edge clk, g, t, rst;
  Ad env;
  MultiOscillator mo;
  Fm2 fm;
  float lfo_ph = 0, rnd = 0, vel = 1, lp = 0;
  int steps = 0;
  Rng r;
  CrustHalf() { mo.Init(SAMPLE_RATE); fm.Init(SAMPLE_RATE); fm.SetRatio(fq31(0.35f)); fm.SetIndex(fq31(0.5f)); }
};
struct Crust2 : Module {
  CrustHalf h[2];
  Crust2() { h[0].r.s ^= 17u; h[1].r.s ^= 31u; }
  void tick(Eng &e, int m) override {
    const int IN_CLK[2] = {CRUST2_IN_A_CLK_IN, CRUST2_IN_B_CLK_IN}, IN_RST[2] = {CRUST2_IN_A_CLK_RESET, CRUST2_IN_B_CLK_RESET},
              IN_C[2] = {CRUST2_IN_A_C_IN, CRUST2_IN_B_C_IN}, IN_G[2] = {CRUST2_IN_A_G_IN, CRUST2_IN_B_G_IN},
              IN_R[2] = {CRUST2_IN_A_R_IN, CRUST2_IN_B_R_IN};
    const int C_PM[2] = {CRUST2_C_A_PITCH_MOD, CRUST2_C_B_PITCH_MOD}, C_SM[2] = {CRUST2_C_A_SAMPLE_MOD, CRUST2_C_B_SAMPLE_MOD},
              C_LM[2] = {CRUST2_C_A_LFO_MOD, CRUST2_C_B_LFO_MOD}, C_CG[2] = {CRUST2_C_A_CVGATE, CRUST2_C_B_CVGATE};
    const int O_OUT[2] = {CRUST2_OUT_A_OUT, CRUST2_OUT_B_OUT}, O_ENV[2] = {CRUST2_OUT_A_ENV, CRUST2_OUT_B_ENV},
              O_CV[2] = {CRUST2_OUT_A_CV, CRUST2_OUT_B_CV}, O_GATE[2] = {CRUST2_OUT_A_GATE, CRUST2_OUT_B_GATE},
              O_EDIT[2] = {CRUST2_OUT_A_EDIT, CRUST2_OUT_B_EDIT};
    float layer = e.ctl(m, CRUST2_C_LAYER), len = e.ctl(m, CRUST2_C_LENGTH), ctrl = e.ctl(m, CRUST2_C_CTRL);
    int bank = (int)e.ctl(m, CRUST2_C_BANK) & 3;
    bool tap = e.take(m, CRUST2_C_TAP);
    for (int v = 0; v < 2; v++) {
      CrustHalf &c = h[v];
      bool trig = c.g.up(e.in(m, IN_G[v]));
      bool clkp = c.clk.up(e.in(m, IN_CLK[v]));
      if (v == 0) trig = c.t.up(e.in(m, CRUST2_IN_A_TRIG)) || trig;
      if (!e.patched_in(m, IN_G[v]) && (v != 0 || !e.patched_in(m, CRUST2_IN_A_TRIG))) trig = trig || clkp;
      if (tap && v == 0) trig = true;
      if (c.rst.up(e.in(m, IN_RST[v])) || c.rst.up(e.in(m, IN_R[v]))) { c.lfo_ph = 0; c.steps = 0; }
      bool hold = e.ctl(m, C_CG[v]) > 0.5f;
      bool gate = hold && e.in(m, IN_G[v]) > 1.0f;
      if (trig) {
        c.vel = (v == 0 && e.patched_in(m, CRUST2_IN_A_VELOCITY)) ? clampf(e.in(m, CRUST2_IN_A_VELOCITY) * 0.2f, 0, 1) : 1.0f;
        c.rnd = c.r.bi() * 5.0f;
        c.mo.Reset(); c.fm.Reset();
        c.steps++;
      }
      c.env.set(0.001f, hold ? 0.0f : 0.0f, 0.03f * exp2f(len * 6.0f));
      c.env.e.SetHold(gate);
      float ev = c.env.run(trig);
      c.lfo_ph += (0.2f + 8.0f * len) / SR; if (c.lfo_ph >= 1) c.lfo_ph -= 1;
      float lfo = sinf(PI2 * c.lfo_ph);
      float pv = (e.ctl(m, C_PM[v]) - 0.5f) * 4.0f + e.in(m, IN_C[v]) + (v == 1 ? e.in(m, CRUST2_IN_B_PITCH_VOCT) : 0.0f) +
                 lfo * e.ctl(m, C_LM[v]);
      float lay = clampf(layer + (v == 0 ? e.in(m, CRUST2_IN_A_LAYER_CTRL) * 0.2f : 0.0f), 0, 1);
      float f = clampf(pitch_hz(pv) * 0.25f * (1.0f + ctrl * 3.0f * ev * ev), 10.0f, 10000.0f);
      float body;
      if (bank == 3) { c.fm.SetFrequency(f); body = q31f(c.fm.Process()); }
      else {
        c.mo.SetFrequency(f);
        MultiOscillator::Outputs o = c.mo.Process();
        body = bank == 0 ? q31f(o.sine) : (bank == 1 ? (std::fabs(q31f(o.ramp)) * 2.0f - 1.0f) : q31f(o.square));
      }
      float n = c.r.bi();
      c.lp += 0.6f * (n - c.lp);
      float noise = n - c.lp;
      float sm = e.ctl(m, C_SM[v]);
      float x = ((1 - sm) * body + sm * noise) * ev * (1.0f - 0.5f * lay) + noise * ev * ev * ev * lay;
      x *= c.vel * 5.0f;
      e.out(m, O_OUT[v], clampf(x, -5, 5));
      e.out(m, O_ENV[v], ev * 5.0f);
      e.out(m, O_CV[v], pv);
      e.out(m, O_GATE[v], (hold ? gate : ev > 0.05f) ? 5.0f : 0.0f);
      e.out(m, O_EDIT[v], lfo * 5.0f);
      if (v == 0) e.out(m, CRUST2_OUT_A_RND_OUT, c.rnd);
      else {
        e.out(m, CRUST2_OUT_B_RND_OUT, c.rnd);
        e.out(m, CRUST2_OUT_B_ENV_OUT1, ev * 5.0f);
        e.out(m, CRUST2_OUT_B_ENV_OUT2, (1.0f - ev) * 5.0f);
      }
    }
  }
};

// ---- Pizza: an FM / wave oscillator on Bastl's Fm2 and MultiOscillator -------------------------------------------------
// PITCH + V/OCT set the pitch; Fm2 (a sine carrier with a modulator at RATIO, up to the carrier's frequency, scaled by
// INDEX = slider + INDEX MOD x FM INDEX input, + EXT) is the voice; SHAPE (slider + knob + CV + CTRL) morphs it into the
// ramp and the pulse of a MultiOscillator; SYNC resets the phase; DETUNE offsets the octave output.
// MAIN = the voice, PULSE = the square, OCT = a sine one octave down.
struct Pizza : Module {
  Fm2 fm;
  MultiOscillator mo, oct;
  Edge sync;
  Pizza() { fm.Init(SAMPLE_RATE); mo.Init(SAMPLE_RATE); oct.Init(SAMPLE_RATE); }
  void tick(Eng &e, int m) override {
    float pv = (e.ctl(m, PIZZA_C_PITCH) - 0.5f) * 6.0f + e.in(m, PIZZA_IN_V_OCT);
    float f = clampf(pitch_hz(pv), 8.0f, 9000.0f);
    if (sync.up(e.in(m, PIZZA_IN_SYNC))) { fm.Reset(); mo.Reset(); }
    fm.SetFrequency(f); mo.SetFrequency(f);
    oct.SetFrequency(clampf(f * 0.5f * (1.0f + (e.ctl(m, PIZZA_C_DETUNE) - 0.5f) * 0.1f), 4.0f, 9000.0f));
    fm.SetRatio(fq31(0.0625f + floorf(e.ctl(m, PIZZA_C_RATIO) * 15.99f) / 16.0f));
    float idx = clampf(e.ctl(m, PIZZA_C_FM_INDEX_SL) + e.ctl(m, PIZZA_C_INDEX_MOD) * e.in(m, PIZZA_IN_FM_INDEX) * 0.2f + e.in(m, PIZZA_IN_EXT) * 0.04f, 0, 1);
    fm.SetIndex(fq31(idx));
    float shape = clampf(e.ctl(m, PIZZA_C_SHAPE_SL) + (e.ctl(m, PIZZA_C_SHAPE) - 0.5f) + e.in(m, PIZZA_IN_CV) * 0.2f + e.in(m, PIZZA_IN_CTRL) * 0.1f, 0, 1) * 2.0f;
    float s0 = q31f(fm.Process());
    MultiOscillator::Outputs o = mo.Process();
    float s1 = q31f(o.ramp), s2 = q31f(o.square);
    float y = shape < 1 ? s0 + (s1 - s0) * shape : s1 + (s2 - s1) * (shape - 1);
    float oc = q31f(oct.Process().sine);
    e.out(m, PIZZA_OUT_MAIN, clampf(y, -1, 1) * 5.0f);
    e.out(m, PIZZA_OUT_PULSE, q31f(o.square) * 5.0f);
    e.out(m, PIZZA_OUT_OCT_OSC, oc * 5.0f);
  }
};

// ---- ABC: six channels, two sums ------------------------------------------------------------------------------------
// The sums go to the Force's audio output 1 (SUM1: A+B+C) and 2 (SUM2: D+E+F) through the engine's mix bus.
struct Abc : Module {
  void tick(Eng &e, int m) override {
    const int r[6] = {ABC_IN_A, ABC_IN_B, ABC_IN_C, ABC_IN_D, ABC_IN_E, ABC_IN_F};
    const int c[6] = {ABC_C_A, ABC_C_B, ABC_C_C, ABC_C_D, ABC_C_E, ABC_C_F};
    float s[2] = {0, 0};
    for (int k = 0; k < 6; k++) s[k / 3] += e.in(m, r[k]) * e.ctl(m, c[k]);
    e.out(m, ABC_OUT_SUM1, s[0]);
    e.out(m, ABC_OUT_SUM2, s[1]);
  }
};

// ---- WaveBard: Bastl's sample player ----------------------------------------------------------------------------------
// Bastl's Wave Bard firmware logic: two SamplePlayers (so a new trigger fades the old sample out), the attack / hold / decay
// envelope and reverse-below-half playback mapped from LENGTH (the firmware's ENVELOPE pot, with its own parameter maps),
// the PITCH pot's map, NOTE (1 V/oct, through the quantizer, scaled by PITCH MOD) and FREE (1 V/oct, not quantised) pitch
// inputs, SAMPLE + SAMPLE MOD + SAMPLE CV, BANK. SHIFT steps the quantizer's scale. Here a trigger is a pulse on G_IN, TRIG,
// MIDI IN, or CLK_IN when none of those is patched. Outputs: OUT = mono, L/R OUT = the stereo sample plus AUD L/R IN.
struct WaveBard : Module {
  SamplePlayer<int16_t> pl[2];
  int active = 0;
  Ad env, fade;
  Quantizer quant;
  Edge clk, g, tr, mi, rst;
  KLfo lfo;
  float fade_max = 0, rnd = 0, last_note = 1.0f;
  int scale = 3;
  bool loaded_scales = false;
  Rng r;
  WaveBard() : lfo(11u) {
    for (int i = 0; i < 2; i++) { pl[i].Init(SAMPLE_RATE, g_bank ? g_bank->rate : SAMPLE_RATE); pl[i].SetHifi(true); }
    fade.set(0.0000001f, 0.0f, 0.01f);
    env.set(0.001f, 0.2f, 0.5f);
    quant.Init();
    if (g_bank) { quant.SetScaleTable(std::span<const Quantizer::Scale>(g_bank->scales, g_bank->nscales)); scale = g_bank->nscales / 2; }
    quant.SetScale(scale);
  }
  void tick(Eng &e, int m) override {
    float sine, tri;
    lfo.run(e, m, e.ctl(m, WAVEBARD_C_LFO), e.in(m, WAVEBARD_IN_LFO_MOD) * e.ctl(m, WAVEBARD_C_LFO_MOD), WAVEBARD_IN_LFO_RESET, WAVEBARD_IN_LFO_IN,
            WAVEBARD_OUT_LFO_L, WAVEBARD_OUT_LFO_A, WAVEBARD_OUT_LFO_OUT, WAVEBARD_OUT_LFO_EDIT, sine, tri);
    bool clkp = clk.up(e.in(m, WAVEBARD_IN_CLK_IN));
    bool trig = g.up(e.in(m, WAVEBARD_IN_G_IN));
    trig = tr.up(e.in(m, WAVEBARD_IN_TRIG)) || trig;
    trig = mi.up(e.in(m, WAVEBARD_IN_MIDI_IN)) || trig;
    if (!e.patched_in(m, WAVEBARD_IN_G_IN) && !e.patched_in(m, WAVEBARD_IN_TRIG) && !e.patched_in(m, WAVEBARD_IN_MIDI_IN)) trig = trig || clkp;
    rst.up(e.in(m, WAVEBARD_IN_CLK_RESET));
    if (e.take(m, WAVEBARD_C_SHIFT) && g_bank) { scale = (scale + 1) % g_bank->nscales; quant.SetScale(scale); }
    bool rnd_cv = e.ctl(m, WAVEBARD_C_RND_CV) > 0.5f, tiv = e.ctl(m, WAVEBARD_C_TIV_GATE) > 0.5f;
    if (!g_bank) return;

    // pitch: the firmware's chain
    float pitch_pot = e.ctl(m, WAVEBARD_C_PITCH);
    float base = curve_map((int32_t)(pitch_pot * POT_MAX), kMapPitch);
    float mod_pot = (curve_map((int32_t)(e.ctl(m, WAVEBARD_C_PITCH_MOD) * POT_MAX), kMapPitchMod) / (float)POT_MAX - 0.5f) * 2.0f;
    float note_v = e.in(m, WAVEBARD_IN_NOTE) * mod_pot;
    base *= exp2f(note_v);
    quant.SetEnabled(e.patched_in(m, WAVEBARD_IN_NOTE));
    base = quant.ProcessMultiplier(base);
    float free_v = e.in(m, WAVEBARD_IN_FREE) * mod_pot;
    if (e.patched_in(m, WAVEBARD_IN_C_IN)) free_v += e.in(m, WAVEBARD_IN_C_IN) * mod_pot;
    base *= exp2f(free_v);
    base = clampf(base, 0.03f, 16.0f);

    // sample / bank
    int nb = g_bank->nbanks, ns = g_bank->nsamples;
    float sel = e.ctl(m, WAVEBARD_C_SAMPLE) + (e.patched_in(m, WAVEBARD_IN_SAMPLE) ? e.in(m, WAVEBARD_IN_SAMPLE) * 0.2f * (e.ctl(m, WAVEBARD_C_SAMPLE_MOD) * 2.0f) : 0.0f);
    int bank = (int)e.ctl(m, WAVEBARD_C_BANK) % nb;
    if (e.patched_in(m, WAVEBARD_IN_BANK)) bank = (int)clampf(e.in(m, WAVEBARD_IN_BANK) * 0.2f * nb, 0, (float)(nb - 1));
    int idx = (int)clampf(sel * (ns - 1) + 0.5f, 0, (float)(ns - 1));

    // envelope (LENGTH = the firmware's ENVELOPE pot)
    float lk = clampf(e.ctl(m, WAVEBARD_C_LENGTH) + e.in(m, WAVEBARD_IN_LENGTH) * 0.2f, 0, 1);
    int32_t lp = (int32_t)(lk * POT_MAX);
    float dec = curve_map(lp, kMapEnvelopeDecay), att = curve_map(lp, kMapEnvelopeAttack), hol = curve_map(lp, kMapEnvelopeHold);
    env.set(att, hol, dec);
    bool reverse = lk < 0.5f;

    if (trig) {
      SamplePlayer<int16_t> &old = pl[active];
      if (old.IsPlaying() && env.e.IsActive()) { fade_max = q31f(env.e.GetOutput()); fade.e.Trigger(); }
      active ^= 1;
      SamplePlayer<int16_t> &p = pl[active];
      const SampleRef &s = g_bank->s[bank][idx];
      SamplePlayer<int16_t>::Sample sm;
      sm.data = s.data; sm.length = s.len; sm.channels = s.ch == 2 ? SamplePlayer<int16_t>::STEREO : SamplePlayer<int16_t>::MONO;
      p.SetSample(sm);
      p.SetReverse(reverse);
      p.SetSpeed(base);
      if (reverse) {
        float adj = (float)p.GetLengthSpeedAdjusted();
        p.SetStartSpeedAdjusted((size_t)clampf(adj - (att + hol) * SAMPLE_RATE, 0.0f, adj));
      } else {
        p.SetStart(0);
      }
      p.Reset();
      p.Play();
      env.e.Trigger();
      rnd = r.bi() * 5.0f;
      last_note = base;
    } else {
      pl[active].SetSpeed(base);
    }
    fade.run(false);
    float ev = q31f(env.e.Process());
    float fv = q31f(fade.e.Process());
    float L = 0, R = 0;
    SamplePlayer<int16_t> &mp = pl[active];
    if (mp.IsPlaying()) { mp.Process(); L = q15f(mp.GetLeft()) * ev; R = q15f(mp.GetRight()) * ev; }
    SamplePlayer<int16_t> &op = pl[active ^ 1];
    if (op.IsPlaying() && fade.e.IsActive()) { op.Process(); float k = fv * fade_max; L += q15f(op.GetLeft()) * k; R += q15f(op.GetRight()) * k; }
    bool playing = mp.IsPlaying() && ev > 0.001f;
    float vo = 0.5f * (L + R) * 5.0f;
    float oL = clampf(L * 5.0f + e.in(m, WAVEBARD_IN_AUD_L_IN), -5, 5), oR = clampf(R * 5.0f + e.in(m, WAVEBARD_IN_AUD_R_IN), -5, 5);
    e.out(m, WAVEBARD_OUT_OUT, clampf(vo, -5, 5));
    e.out(m, WAVEBARD_OUT_L_OUT, oL);
    e.out(m, WAVEBARD_OUT_R_OUT, oR);
    e.out(m, WAVEBARD_OUT_ENV, ev * 5.0f);
    e.out(m, WAVEBARD_OUT_CV, rnd_cv ? rnd : 12.0f / 5.0f * log2f(last_note) / 12.0f * 5.0f / 5.0f);
    e.out(m, WAVEBARD_OUT_GATE, tiv ? (trig ? 5.0f : 0.0f) : (playing ? 5.0f : 0.0f));
  }
};

// ---- Alchemist: a hybrid voice on Bastl's Fm2, MultiOscillator, Svf and envelope --------------------------------------
// TIMBRE (+ SAMPLE jack x TIMBRE MOD + the LFO) sweeps sine -> FM -> ramp -> pulse (+ noise at the top); ENV is the
// decay; a trigger on G_IN / TRIG / MIDI IN / CLK_IN plays it at PITCH + C_IN + NOTE (1 V/oct); the low-pass opens with
// the envelope. TEMPO: free-running trigger rate when CLK IN is not patched and the knob is above half.
struct Alchemist : Module {
  Fm2 fm;
  MultiOscillator mo;
  Svf filt;
  Ad env;
  Edge clk, g, tr, mi;
  KLfo lfo;
  Rng r;
  float rnd = 0, tempo_ph = 0, cvnote = 0;
  Alchemist() : lfo(77u) { fm.Init(SAMPLE_RATE); mo.Init(SAMPLE_RATE); filt.Init(SAMPLE_RATE); filt.SetType(Svf::Type::LOWPASS); filt.SetResonance(0.3f); fm.SetRatio(fq31(0.5f)); r.s ^= 91u; }
  void tick(Eng &e, int m) override {
    float sine, tri;
    lfo.run(e, m, 0.45f, e.in(m, WAVEBARD_IN_LFO_MOD) * e.ctl(m, ALCHEMIST_C_LFO_MOD), WAVEBARD_IN_LFO_RESET, WAVEBARD_IN_LFO_IN,
            WAVEBARD_OUT_LFO_L, WAVEBARD_OUT_LFO_A, WAVEBARD_OUT_LFO_OUT, WAVEBARD_OUT_LFO_EDIT, sine, tri);
    bool clkp = clk.up(e.in(m, ALCHEMIST_IN_CLK_IN));
    bool trig = g.up(e.in(m, ALCHEMIST_IN_G_IN));
    trig = tr.up(e.in(m, ALCHEMIST_IN_TRIG)) || trig;
    trig = mi.up(e.in(m, ALCHEMIST_IN_MIDI_IN)) || trig;
    if (!e.patched_in(m, ALCHEMIST_IN_G_IN) && !e.patched_in(m, ALCHEMIST_IN_TRIG) && !e.patched_in(m, ALCHEMIST_IN_MIDI_IN)) trig = trig || clkp;
    float tk = e.ctl(m, ALCHEMIST_C_TEMPO);
    if (!e.patched_in(m, ALCHEMIST_IN_CLK_IN) && tk > 0.55f) {
      tempo_ph += (0.5f + (tk - 0.55f) * 20.0f) / SR;
      if (tempo_ph >= 1) { tempo_ph -= 1; trig = true; }
    }
    float pv = (e.ctl(m, ALCHEMIST_C_PITCH) - 0.5f) * 4.0f + e.in(m, ALCHEMIST_IN_C_IN) * e.ctl(m, ALCHEMIST_C_PITCH_MOD) * 2.0f + e.in(m, ALCHEMIST_IN_NOTE);
    float t = clampf(e.ctl(m, ALCHEMIST_C_TIMBRE) + e.in(m, ALCHEMIST_IN_SAMPLE) * 0.4f * e.ctl(m, ALCHEMIST_C_TIMBRE_MOD) + tri * e.ctl(m, ALCHEMIST_C_LFO_MOD) * 0.4f, 0, 1);
    float ek = e.ctl(m, ALCHEMIST_C_ENV);
    env.set(0.001f, 0.0f, 0.04f * exp2f(ek * 6.5f));
    if (trig) { rnd = r.bi() * 5.0f; cvnote = pv; }
    float ev = env.run(trig);
    float f = clampf(pitch_hz(pv) * 0.5f, 8.0f, 9000.0f);
    fm.SetFrequency(f); mo.SetFrequency(f);
    fm.SetIndex(fq31(t * t * 1.0f));
    float s0 = q31f(fm.Process());
    MultiOscillator::Outputs o = mo.Process();
    float k = t * 3.0f, y;
    float w1 = q31f(o.ramp), w2 = q31f(o.square);
    if (k < 1) y = s0; else if (k < 2) y = s0 + (w1 - s0) * (k - 1); else y = w1 + (w2 - w1) * (k - 2);
    y += r.bi() * clampf(t - 0.75f, 0, 1) * 1.5f;
    filt.SetFrequency(clampf(250.0f * exp2f(ev * 4.0f + t * 2.0f), 40.0f, 12000.0f));
    float x = q15f(filt.Process(fq15(y * 0.6f))) * 1.6f * ev;
    float vo = clampf(x * 5.0f, -5, 5);
    e.out(m, ALCHEMIST_OUT_OUT, vo);
    e.out(m, ALCHEMIST_OUT_L_OUT, clampf(vo * (1.0f - tri * 0.3f) + e.in(m, ALCHEMIST_IN_AUD_L_IN), -5, 5));
    e.out(m, ALCHEMIST_OUT_R_OUT, clampf(vo * (1.0f + tri * 0.3f) + e.in(m, ALCHEMIST_IN_AUD_R_IN), -5, 5));
    e.out(m, ALCHEMIST_OUT_ENV, ev * 5.0f);
    e.out(m, ALCHEMIST_OUT_CV, e.ctl(m, ALCHEMIST_C_RND_CV) > 0.5f ? rnd : cvnote);
    bool tiv = e.ctl(m, ALCHEMIST_C_TIV_GATE) > 0.5f;
    e.out(m, ALCHEMIST_OUT_GATE, tiv ? (trig ? 5.0f : 0.0f) : (ev > 0.05f ? 5.0f : 0.0f));
  }
};

// ---- Basil: a stereo delay on Bastl's StereoDelay ----------------------------------------------------------------------
// DELAY (+ TIME CV, + V/OCT) sets the time; a clock on SYNC sets it to the period between pulses. FEEDBACK (+CV),
// DRY/WET (+MIX CV), SPACE (right channel's time offset). Switches: STEREO (L and R times differ), SPEED (x2 faster), RANGE
// (short/long), BLUR (soften the repeats), FILTER (Bastl's DJ filter in the loop), TAPS (right at 3/4 of left), LO-FI
// (bit reduction), LONG (x3 time). StereoDelay holds 1.2 s: longer times are clamped.
struct Basil : Module {
  StereoDelay dly;
  Edge sync;
  int since = 0, period = 0;
  float tcur = 0.3f, bl = 0, br = 0;
  Basil() { dly.Init(SAMPLE_RATE); dly.SetFilterResonance(0.2f); }
  void tick(Eng &e, int m) override {
    float inL = e.in(m, BASIL_IN_L_IN), inR = e.patched_in(m, BASIL_IN_R_IN) ? e.in(m, BASIL_IN_R_IN) : inL;
    bool stereo = e.ctl(m, BASIL_C_STEREO) > 0.5f, speed = e.ctl(m, BASIL_C_SPEED) > 0.5f, range = e.ctl(m, BASIL_C_RANGE) > 0.5f,
         blur = e.ctl(m, BASIL_C_BLUR) > 0.5f, filt = e.ctl(m, BASIL_C_FILTER) > 0.5f, taps = e.ctl(m, BASIL_C_TAPS) > 0.5f,
         lofi = e.ctl(m, BASIL_C_LO_FI) > 0.5f, lng = e.ctl(m, BASIL_C_LONG) > 0.5f;
    float tk = clampf(e.ctl(m, BASIL_C_DELAY) + e.in(m, BASIL_IN_TIME_CV) * 0.2f, 0, 1);
    float t = 0.005f + tk * tk * (range ? 1.2f : 0.4f) * (lng ? 3.0f : 1.0f);
    ++since;
    if (sync.up(e.in(m, BASIL_IN_SYNC))) { period = since; since = 0; }
    if (e.patched_in(m, BASIL_IN_SYNC) && period > 100) t = period / SR;
    t *= exp2f(-e.in(m, BASIL_IN_V_OCT));
    if (speed) t *= 0.5f;
    t *= 1.0f + 0.01f * (e.ctl(m, BASIL_C_CTRL) - 0.5f) + e.in(m, BASIL_IN_CTRL) * 0.004f;
    tcur += (t - tcur) * 0.0004f;
    float dl = clampf(tcur * SR, 16.0f, (float)(StereoDelay::kMaxDelay - 8));
    float space = e.ctl(m, BASIL_C_SPACE);
    float dr = taps ? dl * 0.75f : (stereo ? dl * (1.0f + 0.5f * space) : dl * (1.0f + 0.12f * space));
    dly.SetDelay((size_t)dl, (size_t)clampf(dr, 16.0f, (float)(StereoDelay::kMaxDelay - 8)));
    float fb = clampf(e.ctl(m, BASIL_C_FEEDBACK) + e.in(m, BASIL_IN_FEEDBACK_CV) * 0.2f, 0, 1) * (blur ? 0.8f : 0.92f);
    dly.SetFeedback(fq15(fb));
    float mix = clampf(e.ctl(m, BASIL_C_DRY_WET) + e.in(m, BASIL_IN_MIX_CV) * 0.2f, 0, 1);
    dly.SetWet(fq15(mix));
    dly.SetFilterEnabled(filt);
    if (filt) dly.SetFilterCrossfade(fq15(0.35f));
    StereoDelay::Output o = dly.Process(fq15(inL * 0.2f), fq15(inR * 0.2f));
    float oL = q15f(o.left) * 5.0f, oR = q15f(o.right) * 5.0f;
    if (blur) { bl += 0.35f * (oL - bl); br += 0.35f * (oR - br); oL = bl; oR = br; }
    if (lofi) { oL = roundf(oL * 0.4f * 24.0f) / 24.0f * 2.5f; oR = roundf(oR * 0.4f * 24.0f) / 24.0f * 2.5f; }
    e.out(m, BASIL_OUT_L_OUT, clampf(oL, -8, 8));
    e.out(m, BASIL_OUT_R_OUT, clampf(oR, -8, 8));
    e.out(m, BASIL_OUT_MIX_OUT, clampf(0.5f * (oL + oR), -8, 8));
  }
};

// ---- the instance ------------------------------------------------------------------------------------------------------
struct Inst : Eng {
  int block_frames = 128;
  float lim_l = 0, lim_r = 0;
  bool created = false;

  void make_modules(const char *dir) {
    acquire_bank(dir);
    for (int m = 0; m < N_MODS; m++) {
      switch (MOD_TYPE[m]) {
        case T_KOMPAS: { Kompas *k = new Kompas(); k->r.s ^= (uint32_t)(m * 7919 + 1); mod[m] = k; break; }
        case T_CRUST2: mod[m] = new Crust2(); break;
        case T_PIZZA: mod[m] = new Pizza(); break;
        case T_ABC: mod[m] = new Abc(); break;
        case T_WAVEBARD: mod[m] = new WaveBard(); break;
        case T_ALCHEMIST: mod[m] = new Alchemist(); break;
        case T_BASIL: mod[m] = new Basil(); break;
      }
    }
    created = true;
  }
  void free_modules() {
    for (int m = 0; m < N_MODS; m++) { delete mod[m]; mod[m] = nullptr; }
    if (created) release_bank();
    created = false;
  }

  void midi(const uint8_t *msg, int len) {
    if (len < 2) return;
    int st = msg[0] & 0xF0;
    if (st == 0x90 && len >= 3 && msg[2] > 0) { key_note = msg[1]; key_gate = true; bump(); }
    else if (st == 0x80 || (st == 0x90 && len >= 3 && msg[2] == 0)) {
      if (msg[1] == key_note) key_gate = false;
    } else if (st == 0xB0 && len >= 3 && msg[1] == 123) key_gate = false;
  }

  void song_pos(double p, double b, int pl, int frames) {
    ppq = p; bpm = b; playing = pl;
    next_edge = -1;
    if (pl && p >= 0 && b > 1) {
      double spb = SR * 60.0 / b;                      // samples per beat
      edge_step = spb / 4.0;                           // 16th notes
      double q = p * 4.0, c = ceil(q - 1e-9);
      double off = (c - q) * edge_step;
      next_edge = (int)off;
      (void)frames;
    }
  }

  long long frames_run = 0;
  int refreshes = 0;
  void render(int16_t *out_lr, int frames) {
    // ask the host to redraw a few times shortly after loading, so the picture switches (which screen's knobs show) settle
    frames_run += frames;
    if (refreshes < 3 && frames_run > (refreshes == 0 ? 22050LL : refreshes == 1 ? 66150LL : 176400LL)) { refreshes++; bump(); }
    if (!created) { memset(out_lr, 0, sizeof(int16_t) * 2 * frames); return; }
    int pulse = (int)(0.008f * SR);
    for (int i = 0; i < frames; i++) {
      host_clk = false;
      if (next_edge >= 0 && i >= next_edge) {
        host_clk = true;
        next_edge = (int)(next_edge + edge_step);
        if (next_edge <= i) next_edge = i + 1;
      }
      (void)pulse;
      for (int m = 0; m < N_MODS; m++) mod[m]->tick(*this, m);
      float l = 0, r = 0;
      for (int m = 0; m < N_MODS; m++) if (MOD_TYPE[m] == T_ABC) { l += jv[mj_out[m][ABC_OUT_SUM1]]; r += jv[mj_out[m][ABC_OUT_SUM2]]; }
      l *= 0.2f; r *= 0.2f;
      l = tanhf(l); r = tanhf(r);
      out_lr[i * 2] = (int16_t)lrintf(clampf(l, -1, 1) * 32000.0f);
      out_lr[i * 2 + 1] = (int16_t)lrintf(clampf(r, -1, 1) * 32000.0f);
    }
    // a plain edge on the host clock lasts one sample; modules latch it with their own pulse lengths
    if (key_dirty) key_dirty = false;
  }

  // ---- state: the cables and the screen -----------------------------------------------------------------------------
  int save(char *buf, int n) {
    int k = snprintf(buf, n, "kutilxxl;view=%d;", view);
    for (int c = 0; c < ncab && k < n - 90; c++)
      k += snprintf(buf + k, n - k, "cable=%s>%s;", JACK_KEY[cab[c].o], JACK_KEY[cab[c].i]);
    return k;
  }
  void load(const char *st) {
    if (strncmp(st, "kutilxxl", 8)) return;
    ncab = 0;
    const char *q = strchr(st, ';');
    while (q && *++q) {
      const char *e = strchr(q, ';');
      if (!e) break;
      char item[160];
      int len = (int)(e - q) < 159 ? (int)(e - q) : 159;
      memcpy(item, q, len);
      item[len] = 0;
      if (!strncmp(item, "view=", 5)) view = (int)clampf((float)atoi(item + 5), 0, N_SCREENS - 1);
      else if (!strncmp(item, "cable=", 6)) {
        char *gt = strchr(item + 6, '>');
        if (gt) {
          *gt = 0;
          int o = -1, i = -1;
          for (int j = 0; j < N_JACKS; j++) {
            if (!strcmp(JACK_KEY[j], item + 6) && JACK_IS_OUT[j]) o = j;
            if (!strcmp(JACK_KEY[j], gt + 1) && !JACK_IS_OUT[j]) i = j;
          }
          if (o >= 0 && i >= 0) add_cable(o, i);
        }
      }
      q = e;
    }
    held = -1;
    win = -1;
    pv[P_VIEW] = (float)view;
    sync_vw();
    rebuild();
    bump();
  }
};

int find_key(const char *k) {
  static short table[4096];
  static bool built = false;
  auto h = [](const char *s) { uint32_t x = 2166136261u; while (*s) x = (x ^ (unsigned char)*s++) * 16777619u; return x; };
  if (!built) {
    for (int i = 0; i < 4096; i++) table[i] = -1;
    for (int i = 0; i < P_COUNT; i++) {
      uint32_t s = h(P_KEY[i]) & 4095;
      while (table[s] >= 0) s = (s + 1) & 4095;
      table[s] = (short)i;
    }
    built = true;
  }
  uint32_t s = h(k) & 4095;
  while (table[s] >= 0) {
    if (!strcmp(P_KEY[table[s]], k)) return table[s];
    s = (s + 1) & 4095;
  }
  return -1;
}

int ql_target(const Inst *s, int q) { return SCREEN_QLINKS[s->view][q]; }

void display_text(const Inst *s, int p, char *buf, int n) {
  if (P_INT[p]) snprintf(buf, n, "%d", (int)s->pv[p] + 1);
  else snprintf(buf, n, "%d%%", (int)lroundf(s->pv[p] * 100.0f));
}

// ---- mpc_engine glue ---------------------------------------------------------------------------------------------------
void *create(const char *data_dir) {
  void *mem = calloc(1, sizeof(Inst));
  if (!mem) return nullptr;
  Inst *s = new (mem) Inst();
  s->init();
  s->make_modules(data_dir);
  return s;
}

void destroy(void *inst) {
  Inst *s = (Inst *)inst;
  s->free_modules();
  s->~Inst();
  free(s);
}

void midi(void *inst, const uint8_t *m, int len) { ((Inst *)inst)->midi(m, len); }

void set_param(void *inst, const char *key, const char *val) {
  Inst *s = (Inst *)inst;
  float v = (float)atof(val);
  if (!strcmp(key, "state")) { s->load(val); return; }
  if (!strcmp(key, "transport")) return;
  int p = find_key(key);
  if (p < 0) return;
  if (p < N_CONTROLS) {
    if (P_TRIG[p]) { if (v > 0.5f) s->btn[p] = 1; return; }
    s->set_control(p, v);
    s->bump();
    return;
  }
  if (p == P_VIEW) { s->set_view((int)lroundf(v)); return; }
  if (p >= P_QL1 && p <= P_QL16) {
    int t = ql_target(s, p - P_QL1);
    if (t < 0) return;
    s->set_control(t, P_MIN[t] + clampf(v, 0, 1) * (P_MAX[t] - P_MIN[t]));
    s->bump();
    return;
  }
  if (v < 0.5f) return;                      // triggers fire on 1 only
  if (p == P_NAV_PREV || p == P_NAV_NEXT) {
    int n = s->view + (p == P_NAV_NEXT ? 1 : -1);
    if (n < 0) n = N_SCREENS - 1;
    if (n >= N_SCREENS) n = 0;
    s->set_view(n);
    return;
  }
  if (p >= P_TAP_FIRST && p < P_TAP_FIRST + N_JACKS) { s->tap(p - P_TAP_FIRST); return; }
  if (p >= P_MW_FIRST && p < P_MW_FIRST + N_MODS) { s->open_win(p - P_MW_FIRST); return; }
  if (p == P_MCLOSE) { s->close_win(); return; }
}

int get_param(void *inst, const char *key, char *buf, int n) {
  Inst *s = (Inst *)inst;
  if (!strcmp(key, "display_rev")) return snprintf(buf, n, "%u", s->rev);
  if (!strcmp(key, "state")) return s->save(buf, n);
  size_t kl = strlen(key);
  char base[96];
  int suffix = 0;   // 1 = _display, 2 = _name
  if (kl > 8 && !strcmp(key + kl - 8, "_display")) { suffix = 1; kl -= 8; }
  else if (kl > 5 && !strcmp(key + kl - 5, "_name")) { suffix = 2; kl -= 5; }
  if (kl >= sizeof base) return 0;
  memcpy(base, key, kl);
  base[kl] = 0;
  int p = find_key(base);
  if (p < 0) return 0;
  if (p >= P_QL1 && p <= P_QL16) {
    int t = ql_target(s, p - P_QL1);
    if (suffix == 2) return snprintf(buf, n, "%s", t >= 0 ? P_NAME[t] : "-");
    if (suffix == 1) { if (t < 0) return snprintf(buf, n, " "); display_text(s, t, buf, n); return (int)strlen(buf); }
    if (t < 0) return snprintf(buf, n, "0");
    float span = P_MAX[t] - P_MIN[t];
    return snprintf(buf, n, "%g", span > 0 ? (s->pv[t] - P_MIN[t]) / span : 0.0f);
  }
  if (suffix == 2) return 0;
  if (suffix == 1) {
    if (p >= N_CONTROLS) return 0;
    display_text(s, p, buf, n);
    return (int)strlen(buf);
  }
  if (p < N_CONTROLS) return P_NOPTS[p] ? snprintf(buf, n, "%d", (int)s->pv[p]) : snprintf(buf, n, "%g", s->pv[p]);
  if (p == P_VIEW) return snprintf(buf, n, "%d", s->view);
  if (p == P_VW) return snprintf(buf, n, "%d", s->win >= 0 ? N_SCREENS + s->win : s->view);
  if (p >= P_VIS_FIRST && p < P_VIS_FIRST + N_VIS) return snprintf(buf, n, "%d", s->vis_value(p - P_VIS_FIRST));
  if (p == P_PATCH_INFO) return snprintf(buf, n, "%s", s->info);
  return snprintf(buf, n, "0");
}

void render(void *inst, int16_t *out, int frames) { ((Inst *)inst)->render(out, frames); }
void song_pos(void *inst, double ppq, double bpm, int playing, int frames) { ((Inst *)inst)->song_pos(ppq, bpm, playing, frames); }

const mpc_engine_t API = {create, destroy, midi, set_param, get_param, render, nullptr, song_pos};

}  // namespace

extern "C" const mpc_engine_t *mpc_engine(void) { return &API; }

