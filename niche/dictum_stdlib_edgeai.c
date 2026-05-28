/*
 * Dictum Niche Standard Library — Edge AI / ML Implementation
 * 
 * This file provides the safety wrapper around inference backends.
 * Actual inference is delegated to:
 *   - llama.cpp        (LLM module)
 *   - whisper.cpp      (Speech module)
 *   - stable-diffusion.cpp (Diffusion module)
 *   - ONNX Runtime     (Runtime module)
 * 
 * Safety enforced here:
 *   - Path validation before model load
 *   - Context/temperature clamping per target
 *   - Memory budget enforcement
 *   - Linear ownership of handles
 *   - KV cache auto-clear on unload
 */

#include "dictum_stdlib_edgeai.h"
#include <string.h>
#include <math.h>

/* =============================================================================
 * PLATFORM BUDGETS (from dictum_stdlib_core.h defines)
 * ============================================================================= */

static dictum_count dictum_llm_max_context(void) {
    #if defined(DICTUM_TARGET_ESP32S3)
        return 2048;  /* PSRAM limited */
    #elif defined(DICTUM_TARGET_PI5)
        return 32768; /* 8GB RAM */
    #elif defined(DICTUM_TARGET_PI_ZERO_2W)
        return 2048;  /* 512MB RAM, 3B param limit */
    #elif defined(DICTUM_TARGET_STM32H7)
        return 512;   /* Only with SDRAM */
    #else
        return 0;     /* LLM not available */
    #endif
}

static dictum_count dictum_diffusion_max_res(void) {
    #if defined(DICTUM_TARGET_ESP32S3)
        return 256;   /* PSRAM limited */
    #elif defined(DICTUM_TARGET_PI5)
        return 1024;
    #elif defined(DICTUM_TARGET_PI_ZERO_2W)
        return 512;
    #else
        return 0;
    #endif
}

static bool dictum_llm_available(void) {
    return dictum_llm_max_context() > 0;
}

static bool dictum_diffusion_available(void) {
    return dictum_diffusion_max_res() > 0;
}

/* =============================================================================
 * LLM MODULE IMPLEMENTATION
 * ============================================================================= */

struct dictum_llm_ctx {
    char path[256];
    dictum_llm_config cfg;
    void* backend_ctx;   /* Opaque pointer to llama_context* etc. */
    bool loaded;
};

/* Clamp config to platform limits */
static void dictum_llm_clamp_config(dictum_llm_config* cfg) {
    dictum_count max_ctx = dictum_llm_max_context();
    if (cfg->context > max_ctx) cfg->context = max_ctx;
    if (cfg->temperature > 2000) cfg->temperature = 2000;
    if (cfg->temperature < 0) cfg->temperature = 0;
    if (cfg->top_p > 1000) cfg->top_p = 1000;
    if (cfg->top_p < 0) cfg->top_p = 0;
}

dictum_result dictum_llm_load(const char* path, dictum_llm_config* config, dictum_llm_handle* out) {
    if (!out) return dictum_err("null output pointer");
    if (!config) return dictum_err("null config");
    if (!dictum_path_valid(path)) return dictum_err("invalid model path");
    if (!dictum_llm_available()) return dictum_err("LLM not available on this target");

    dictum_llm_clamp_config(config);

    dictum_llm_handle h = (dictum_llm_handle)dictum_alloc(sizeof(struct dictum_llm_ctx));
    if (!h) return dictum_err("allocation failed");

    dictum_strncpy(h->path, path, sizeof(h->path));
    h->cfg = *config;
    h->backend_ctx = NULL;  /* TODO: integrate llama.cpp loading here */
    h->loaded = true;

    dictum_handle_register(h, "llm", path);
    *out = h;
    return dictum_ok();
}

dictum_count dictum_llm_token_count(dictum_llm_handle h) {
    if (!h || !h->loaded) return 0;
    /* TODO: call llama_get_kv_cache_token_count or equivalent */
    return 0;
}

dictum_result dictum_llm_prompt(dictum_llm_handle h, const char* text) {
    if (!h || !h->loaded) return dictum_err("invalid handle");
    if (!text) return dictum_err("null prompt");
    (void)text;
    /* TODO: tokenize and eval prompt tokens */
    return dictum_ok();
}

dictum_text dictum_llm_generate(dictum_llm_handle h, dictum_count max_tokens) {
    if (!h || !h->loaded) return NULL;
    (void)max_tokens;
    /* TODO: sampling loop via llama.cpp */
    static char buf[1024];
    dictum_strncpy(buf, "[generated text placeholder]", sizeof(buf));
    return buf;
}

dictum_text dictum_llm_chat(dictum_llm_handle h, const char* role, const char* message) {
    if (!h || !h->loaded) return NULL;
    if (!role || !message) return NULL;
    (void)role; (void)message;
    /* TODO: format chat template and generate */
    static char buf[1024];
    dictum_strncpy(buf, "[chat response placeholder]", sizeof(buf));
    return buf;
}

dictum_result dictum_llm_embed(dictum_llm_handle h, const char* text) {
    if (!h || !h->loaded) return dictum_err("invalid handle");
    if (!text) return dictum_err("null text");
    (void)text;
    /* TODO: embedding extraction */
    return dictum_ok();
}

void dictum_llm_kv_clear(dictum_llm_handle h) {
    if (!h || !h->loaded) return;
    /* TODO: llama_kv_cache_clear() */
}

void dictum_llm_unload(dictum_llm_handle h) {
    if (!h) return;
    if (!dictum_handle_is_alive(h)) {
        /* Double-unload detected — log and ignore (validator should prevent this) */
        DICTUM_LOG("double-unload of LLM handle %p", (void*)h);
        return;
    }
    dictum_llm_kv_clear(h);
    h->loaded = false;
    dictum_handle_mark_released(h);
    /* TODO: free backend_ctx via llama_free() */
    dictum_free(h);
}

/* =============================================================================
 * SPEECH MODULE IMPLEMENTATION
 * ============================================================================= */

struct dictum_speech_ctx {
    char path[256];
    dictum_speech_config cfg;
    void* backend_ctx;
    bool loaded;
};

struct dictum_stream_ctx {
    dictum_speech_handle parent;
    dictum_count chunk_ms;
    dictum_handle audio_buffer;
    bool active;
};

static void dictum_speech_clamp_config(dictum_speech_config* cfg) {
    (void)cfg;  /* Language validated at runtime */
}

dictum_result dictum_speech_load(const char* path, dictum_speech_config* config, dictum_speech_handle* out) {
    if (!out || !config) return dictum_err("null argument");
    if (!dictum_path_valid(path)) return dictum_err("invalid model path");

    dictum_speech_handle h = (dictum_speech_handle)dictum_alloc(sizeof(struct dictum_speech_ctx));
    if (!h) return dictum_err("allocation failed");

    dictum_speech_clamp_config(config);
    dictum_strncpy(h->path, path, sizeof(h->path));
    h->cfg = *config;
    h->backend_ctx = NULL;  /* TODO: whisper.cpp init */
    h->loaded = true;

    dictum_handle_register(h, "speech", path);
    *out = h;
    return dictum_ok();
}

dictum_text dictum_speech_transcribe(dictum_speech_handle h, dictum_handle audio) {
    if (!h || !h->loaded) return NULL;
    if (!audio) return NULL;
    (void)audio;
    /* TODO: whisper_full() */
    static char buf[512];
    dictum_strncpy(buf, "[transcription]", sizeof(buf));
    return buf;
}

dictum_text dictum_speech_translate(dictum_speech_handle h, dictum_handle audio) {
    if (!h || !h->loaded) return NULL;
    if (!audio) return NULL;
    (void)audio;
    static char buf[512];
    dictum_strncpy(buf, "[translation]", sizeof(buf));
    return buf;
}

dictum_result dictum_speech_stream_init(dictum_speech_handle h, dictum_count chunk_ms, dictum_stream_handle* out) {
    if (!h || !h->loaded) return dictum_err("invalid handle");
    if (chunk_ms < 100 || chunk_ms > 30000) return dictum_err("chunk_ms out of bounds 100-30000");
    if (!out) return dictum_err("null output");

    dictum_stream_handle s = (dictum_stream_handle)dictum_alloc(sizeof(struct dictum_stream_ctx));
    if (!s) return dictum_err("allocation failed");

    s->parent = h;
    s->chunk_ms = chunk_ms;
    s->audio_buffer = NULL;
    s->active = true;

    dictum_handle_register(s, "speech_stream", "stream");
    *out = s;
    return dictum_ok();
}

void dictum_speech_stream_feed(dictum_stream_handle s, dictum_handle audio) {
    if (!s || !s->active) return;
    if (!audio) return;
    /* TODO: accumulate audio into ring buffer */
    (void)audio;
}

dictum_text dictum_speech_stream_read(dictum_stream_handle s) {
    if (!s || !s->active) return NULL;
    /* TODO: process buffered audio */
    static char buf[512];
    dictum_strncpy(buf, "", sizeof(buf));
    return buf;
}

void dictum_speech_stream_end(dictum_stream_handle s) {
    if (!s) return;
    s->active = false;
    if (s->audio_buffer) {
        dictum_free(s->audio_buffer);
        s->audio_buffer = NULL;
    }
    dictum_handle_mark_released(s);
    dictum_free(s);
}

void dictum_speech_unload(dictum_speech_handle h) {
    if (!h) return;
    if (!dictum_handle_is_alive(h)) {
        DICTUM_LOG("double-unload of speech handle %p", (void*)h);
        return;
    }
    h->loaded = false;
    dictum_handle_mark_released(h);
    /* TODO: whisper_free() */
    dictum_free(h);
}

/* =============================================================================
 * DIFFUSION MODULE IMPLEMENTATION
 * ============================================================================= */

struct dictum_diffusion_ctx {
    char path[256];
    dictum_diffusion_config cfg;
    void* backend_ctx;
    bool loaded;
};

struct dictum_image {
    dictum_count width;
    dictum_count height;
    dictum_handle pixels;  /* RGBA buffer */
};

static void dictum_diffusion_clamp_config(dictum_diffusion_config* cfg) {
    dictum_count max_res = dictum_diffusion_max_res();
    if (cfg->width > max_res) cfg->width = max_res;
    if (cfg->height > max_res) cfg->height = max_res;
    if (cfg->steps < 1) cfg->steps = 1;
    if (cfg->steps > 50) cfg->steps = 50;
}

dictum_result dictum_diffusion_load(const char* path, dictum_diffusion_config* config, dictum_diffusion_handle* out) {
    if (!out || !config) return dictum_err("null argument");
    if (!dictum_path_valid(path)) return dictum_err("invalid model path");
    if (!dictum_diffusion_available()) return dictum_err("diffusion not available on this target");

    dictum_diffusion_clamp_config(config);
    if (config->width == 0 || config->height == 0) {
        return dictum_err("width/height must be > 0");
    }

    dictum_diffusion_handle h = (dictum_diffusion_handle)dictum_alloc(sizeof(struct dictum_diffusion_ctx));
    if (!h) return dictum_err("allocation failed");

    dictum_strncpy(h->path, path, sizeof(h->path));
    h->cfg = *config;
    h->backend_ctx = NULL;  /* TODO: stable-diffusion.cpp init */
    h->loaded = true;

    dictum_handle_register(h, "diffusion", path);
    *out = h;
    return dictum_ok();
}

dictum_result dictum_diffusion_txt2img(dictum_diffusion_handle h, const char* prompt, const char* negative, dictum_image_handle* out) {
    if (!h || !h->loaded) return dictum_err("invalid handle");
    if (!prompt) return dictum_err("null prompt");
    if (!out) return dictum_err("null output");
    (void)negative;

    dictum_image_handle img = (dictum_image_handle)dictum_alloc(sizeof(struct dictum_image));
    if (!img) return dictum_err("allocation failed");

    img->width = h->cfg.width;
    img->height = h->cfg.height;
    size_t pixel_bytes = (size_t)img->width * img->height * 4;
    img->pixels = dictum_alloc(pixel_bytes);
    if (!img->pixels) {
        dictum_free(img);
        return dictum_err("pixel allocation failed");
    }

    /* TODO: run stable-diffusion.cpp inference */

    dictum_handle_register(img, "image", "txt2img");
    *out = img;
    return dictum_ok();
}

dictum_result dictum_diffusion_img2img(dictum_diffusion_handle h, dictum_image_handle img, dictum_whole strength, dictum_image_handle* out) {
    if (!h || !h->loaded) return dictum_err("invalid handle");
    if (!img || !img->pixels) return dictum_err("invalid image");
    if (!out) return dictum_err("null output");
    if (strength > 1000) strength = 1000;
    (void)strength;

    dictum_image_handle result = (dictum_image_handle)dictum_alloc(sizeof(struct dictum_image));
    if (!result) return dictum_err("allocation failed");

    result->width = img->width;
    result->height = img->height;
    size_t pixel_bytes = (size_t)result->width * result->height * 4;
    result->pixels = dictum_alloc(pixel_bytes);
    if (!result->pixels) {
        dictum_free(result);
        return dictum_err("pixel allocation failed");
    }

    /* TODO: img2img pipeline */

    dictum_handle_register(result, "image", "img2img");
    *out = result;
    return dictum_ok();
}

dictum_result dictum_diffusion_upscale(dictum_diffusion_handle h, dictum_image_handle img, dictum_count scale, dictum_image_handle* out) {
    if (!h || !h->loaded) return dictum_err("invalid handle");
    if (!img || !img->pixels) return dictum_err("invalid image");
    if (!out) return dictum_err("null output");
    if (scale == 0) scale = 1;

    dictum_image_handle result = (dictum_image_handle)dictum_alloc(sizeof(struct dictum_image));
    if (!result) return dictum_err("allocation failed");

    result->width = img->width * scale;
    result->height = img->height * scale;
    size_t pixel_bytes = (size_t)result->width * result->height * 4;
    result->pixels = dictum_alloc(pixel_bytes);
    if (!result->pixels) {
        dictum_free(result);
        return dictum_err("pixel allocation failed");
    }

    /* TODO: upscale pipeline */

    dictum_handle_register(result, "image", "upscale");
    *out = result;
    return dictum_ok();
}

dictum_result dictum_diffusion_save(dictum_image_handle img, const char* path) {
    if (!img || !img->pixels) return dictum_err("invalid image");
    if (!dictum_path_valid(path)) return dictum_err("invalid path");
    if (!dictum_path_in_scope(path, "/sd/") && !dictum_path_in_scope(path, "/tmp/")) {
        return dictum_err("path must be in /sd/ or /tmp/");
    }
    (void)img; (void)path;
    /* TODO: BMP/PNG encoding and write */
    return dictum_ok();
}

void dictum_diffusion_free(dictum_image_handle img) {
    if (!img) return;
    if (img->pixels) {
        dictum_free(img->pixels);
        img->pixels = NULL;
    }
    dictum_handle_mark_released(img);
    dictum_free(img);
}

void dictum_diffusion_unload(dictum_diffusion_handle h) {
    if (!h) return;
    if (!dictum_handle_is_alive(h)) {
        DICTUM_LOG("double-unload of diffusion handle %p", (void*)h);
        return;
    }
    h->loaded = false;
    dictum_handle_mark_released(h);
    /* TODO: sd_free() */
    dictum_free(h);
}

/* =============================================================================
 * RUNTIME MODULE IMPLEMENTATION (ONNX Runtime)
 * ============================================================================= */

struct dictum_onnx_ctx {
    char path[256];
    char backend[32];
    void* session;   /* OrtSession* */
    bool active;
};

struct dictum_tensor {
    dictum_tensor_desc desc;
    void* data;
    size_t data_bytes;
};

static bool dictum_runtime_backend_valid(const char* backend) {
    /* Compile-time support matrix check */
    #if defined(DICTUM_TARGET_PI5)
        (void)backend;
        return true;
    #elif defined(DICTUM_TARGET_STM32H7) || defined(DICTUM_TARGET_STM32F4)
        return dictum_strcmp(backend, "cmsis_nn") == 0;
    #elif defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        return dictum_strcmp(backend, "xnnpack") == 0 || dictum_strcmp(backend, "cpu") == 0;
    #else
        return dictum_strcmp(backend, "cpu") == 0;
    #endif
}

static size_t dictum_tensor_kind_size(const char* kind) {
    if (dictum_strcmp(kind, "float32") == 0) return 4;
    if (dictum_strcmp(kind, "float16") == 0) return 2;
    if (dictum_strcmp(kind, "int8") == 0) return 1;
    if (dictum_strcmp(kind, "uint8") == 0) return 1;
    return 4;
}

static bool dictum_runtime_kind_valid_for_target(const char* kind) {
    if (dictum_strcmp(kind, "float16") == 0) {
        #if defined(DICTUM_TARGET_RP2040) || defined(DICTUM_TARGET_STM32F4)
            return false;  /* No FP16 hardware support */
        #endif
    }
    return true;
}

dictum_result dictum_runtime_session(const char* path, const char* backend, dictum_session_handle* out) {
    if (!out || !backend) return dictum_err("null argument");
    if (!dictum_path_valid(path)) return dictum_err("invalid model path");
    if (!dictum_runtime_backend_valid(backend)) return dictum_err("backend not supported on target");

    dictum_session_handle s = (dictum_session_handle)dictum_alloc(sizeof(struct dictum_onnx_ctx));
    if (!s) return dictum_err("allocation failed");

    dictum_strncpy(s->path, path, sizeof(s->path));
    dictum_strncpy(s->backend, backend, sizeof(s->backend));
    s->session = NULL;  /* TODO: OrtCreateSession() */
    s->active = true;

    dictum_handle_register(s, "onnx_session", path);
    *out = s;
    return dictum_ok();
}

dictum_count dictum_runtime_input_count(dictum_session_handle h) {
    if (!h || !h->active) return 0;
    /* TODO: OrtSessionGetInputCount() */
    return 1;
}

dictum_count dictum_runtime_output_count(dictum_session_handle h) {
    if (!h || !h->active) return 0;
    /* TODO: OrtSessionGetOutputCount() */
    return 1;
}

dictum_text dictum_runtime_input_name(dictum_session_handle h, dictum_count idx) {
    if (!h || !h->active) return NULL;
    (void)idx;
    static char buf[64];
    dictum_strncpy(buf, "input", sizeof(buf));
    return buf;
}

dictum_text dictum_runtime_output_name(dictum_session_handle h, dictum_count idx) {
    if (!h || !h->active) return NULL;
    (void)idx;
    static char buf[64];
    dictum_strncpy(buf, "output", sizeof(buf));
    return buf;
}

dictum_result dictum_runtime_tensor(dictum_tensor_desc* desc, dictum_tensor_handle* out) {
    if (!desc || !out) return dictum_err("null argument");
    if (desc->dims < 1 || desc->dims > 4) return dictum_err("dims must be 1-4");
    if (!dictum_runtime_kind_valid_for_target(desc->kind)) return dictum_err("tensor kind not supported on target");

    dictum_tensor_handle t = (dictum_tensor_handle)dictum_alloc(sizeof(struct dictum_tensor));
    if (!t) return dictum_err("allocation failed");

    t->desc = *desc;
    size_t elem_size = dictum_tensor_kind_size(desc->kind);
    size_t count = 1;
    dictum_count dims[] = {desc->d_0, desc->d_1, desc->d_2, desc->d_3};
    for (int __d = 0; __d < (int)desc->dims; __d++) {
        count *= dims[__d];
    }
    size_t total = count * elem_size;

    /* Memory budget enforcement per target */
    #if defined(DICTUM_TARGET_RP2040)
        if (total > 64 * 1024) {
            dictum_free(t);
            return dictum_err("tensor exceeds RP2040 budget (64KB)");
        }
    #elif defined(DICTUM_TARGET_ESP32)
        if (total > 128 * 1024) {
            dictum_free(t);
            return dictum_err("tensor exceeds ESP32 budget (128KB)");
        }
    #endif

    t->data = dictum_alloc(total);
    if (!t->data) {
        dictum_free(t);
        return dictum_err("tensor data allocation failed");
    }
    t->data_bytes = total;

    dictum_handle_register(t, "tensor", "runtime");
    *out = t;
    return dictum_ok();
}

void dictum_runtime_tensor_set(dictum_tensor_handle t, dictum_count idx, dictum_whole value) {
    if (!t || !t->data) return;
    /* Bounds check: verify idx against tensor dimensions */
    size_t count = 1;
    dictum_count __tdims[] = {t->desc.d_0, t->desc.d_1, t->desc.d_2, t->desc.d_3};
    for (int __d = 0; __d < (int)t->desc.dims; __d++) {
        count *= __tdims[__d];
    }
    if ((size_t)idx >= count) {
        DICTUM_LOG("tensor_set OOB: idx=%u >= count=%zu", (unsigned)idx, count);
        return;
    }
    /* TODO: kind-aware write (float32, int8, etc.) */
    ((dictum_whole*)t->data)[idx] = value;
}

dictum_whole dictum_runtime_tensor_get(dictum_tensor_handle t, dictum_count idx) {
    if (!t || !t->data) return 0;
    size_t count = 1;
    dictum_count __tdims[] = {t->desc.d_0, t->desc.d_1, t->desc.d_2, t->desc.d_3};
    for (int __d = 0; __d < (int)t->desc.dims; __d++) {
        count *= __tdims[__d];
    }
    if ((size_t)idx >= count) {
        DICTUM_LOG("tensor_get OOB: idx=%u >= count=%zu", (unsigned)idx, count);
        return 0;
    }
    return ((dictum_whole*)t->data)[idx];
}

dictum_result dictum_runtime_run(dictum_session_handle s, dictum_tensor_handle input, dictum_tensor_handle* output) {
    if (!s || !s->active) return dictum_err("invalid session");
    if (!input || !input->data) return dictum_err("invalid input tensor");
    if (!output) return dictum_err("null output");
    (void)input;

    /* Create output tensor */
    dictum_tensor_desc out_desc = {
        .dims = 1, .d_0 = 1, .d_1 = 0, .d_2 = 0, .d_3 = 0,
        .kind = "float32"
    };
    dictum_tensor_handle out = NULL;
    dictum_result r = dictum_runtime_tensor(&out_desc, &out);
    if (!r.ok) return r;

    /* TODO: OrtRun() */

    *output = out;
    return dictum_ok();
}

void dictum_runtime_tensor_free(dictum_tensor_handle t) {
    if (!t) return;
    if (t->data) {
        dictum_free(t->data);
        t->data = NULL;
    }
    dictum_handle_mark_released(t);
    dictum_free(t);
}

void dictum_runtime_session_free(dictum_session_handle s) {
    if (!s) return;
    if (!dictum_handle_is_alive(s)) {
        DICTUM_LOG("double-free of session handle %p", (void*)s);
        return;
    }
    s->active = false;
    dictum_handle_mark_released(s);
    /* TODO: OrtReleaseSession() */
    dictum_free(s);
}
