/*
 * Dictum Niche Standard Library — Edge AI / ML Modules
 * Modules: LLM, Speech, Diffusion, Runtime (ONNX)
 */

#ifndef DICTUM_STDLIB_EDGEAI_H
#define DICTUM_STDLIB_EDGEAI_H

#include "dictum_stdlib_core.h"

#ifdef __cplusplus
extern "C" {
#endif

/* =============================================================================
 * MODULE: LLM (backend: llama.cpp)
 * ============================================================================= */

typedef struct {
    dictum_count context;
    dictum_whole temperature;   /* 0-2000 represents 0.0-2.0 */
    dictum_whole top_p;           /* 0-1000 represents 0.0-1.0 */
    dictum_count seed;
    char backend[16];           /* "cpu", "cuda", "metal", "vulkan" */
} dictum_llm_config;

typedef struct dictum_llm_ctx* dictum_llm_handle;

dictum_result dictum_llm_load(const char* path, dictum_llm_config* config, dictum_llm_handle* out);
dictum_count dictum_llm_token_count(dictum_llm_handle h);
dictum_result dictum_llm_prompt(dictum_llm_handle h, const char* text);
dictum_text dictum_llm_generate(dictum_llm_handle h, dictum_count max_tokens);
dictum_text dictum_llm_chat(dictum_llm_handle h, const char* role, const char* message);
dictum_result dictum_llm_embed(dictum_llm_handle h, const char* text);
void dictum_llm_kv_clear(dictum_llm_handle h);
void dictum_llm_unload(dictum_llm_handle h);

/* =============================================================================
 * MODULE: Speech (backend: whisper.cpp)
 * ============================================================================= */

typedef struct {
    char language[8];           /* "en", "ja", "auto" */
    dictum_truth translate;     /* translate to English? */
    char backend[16];           /* "cpu", "cuda", "coreml" */
} dictum_speech_config;

typedef struct dictum_speech_ctx* dictum_speech_handle;
typedef struct dictum_stream_ctx* dictum_stream_handle;

dictum_result dictum_speech_load(const char* path, dictum_speech_config* config, dictum_speech_handle* out);
dictum_text dictum_speech_transcribe(dictum_speech_handle h, dictum_handle audio);
dictum_text dictum_speech_translate(dictum_speech_handle h, dictum_handle audio);
dictum_result dictum_speech_stream_init(dictum_speech_handle h, dictum_count chunk_ms, dictum_stream_handle* out);
void dictum_speech_stream_feed(dictum_stream_handle s, dictum_handle audio);
dictum_text dictum_speech_stream_read(dictum_stream_handle s);
void dictum_speech_stream_end(dictum_stream_handle s);
void dictum_speech_unload(dictum_speech_handle h);

/* =============================================================================
 * MODULE: Diffusion (backend: stable-diffusion.cpp)
 * ============================================================================= */

typedef struct {
    dictum_count width;
    dictum_count height;
    dictum_count steps;         /* 1-50 */
    dictum_count seed;
    char backend[16];           /* "cpu", "cuda", "metal" */
} dictum_diffusion_config;

typedef struct dictum_diffusion_ctx* dictum_diffusion_handle;
typedef struct dictum_image* dictum_image_handle;

dictum_result dictum_diffusion_load(const char* path, dictum_diffusion_config* config, dictum_diffusion_handle* out);
dictum_result dictum_diffusion_txt2img(dictum_diffusion_handle h, const char* prompt, const char* negative, dictum_image_handle* out);
dictum_result dictum_diffusion_img2img(dictum_diffusion_handle h, dictum_image_handle img, dictum_whole strength, dictum_image_handle* out);
dictum_result dictum_diffusion_upscale(dictum_diffusion_handle h, dictum_image_handle img, dictum_count scale, dictum_image_handle* out);
dictum_result dictum_diffusion_save(dictum_image_handle img, const char* path);
void dictum_diffusion_free(dictum_image_handle img);
void dictum_diffusion_unload(dictum_diffusion_handle h);

/* =============================================================================
 * MODULE: Runtime (backend: ONNX Runtime)
 * ============================================================================= */

typedef struct {
    dictum_count dims;
    dictum_count d_0;
    dictum_count d_1;
    dictum_count d_2;
    dictum_count d_3;
    char kind[16];              /* "float32", "int8", "uint8", "float16" */
} dictum_tensor_desc;

typedef struct dictum_onnx_ctx* dictum_session_handle;
typedef struct dictum_tensor* dictum_tensor_handle;

dictum_result dictum_runtime_session(const char* path, const char* backend, dictum_session_handle* out);
dictum_count dictum_runtime_input_count(dictum_session_handle h);
dictum_count dictum_runtime_output_count(dictum_session_handle h);
dictum_text dictum_runtime_input_name(dictum_session_handle h, dictum_count idx);
dictum_text dictum_runtime_output_name(dictum_session_handle h, dictum_count idx);
dictum_result dictum_runtime_tensor(dictum_tensor_desc* desc, dictum_tensor_handle* out);
void dictum_runtime_tensor_set(dictum_tensor_handle t, dictum_count idx, dictum_whole value);
dictum_whole dictum_runtime_tensor_get(dictum_tensor_handle t, dictum_count idx);
dictum_result dictum_runtime_run(dictum_session_handle s, dictum_tensor_handle input, dictum_tensor_handle* output);
void dictum_runtime_tensor_free(dictum_tensor_handle t);
void dictum_runtime_session_free(dictum_session_handle s);

#ifdef __cplusplus
}
#endif

#endif /* DICTUM_STDLIB_EDGEAI_H */
