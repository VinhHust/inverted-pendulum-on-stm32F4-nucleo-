/**
 ******************************************************************************
 * @file    stepper_tb6600.c
 * @brief   TB6600 Stepper Driver Library - Implementation
 ******************************************************************************
 */

#include <librarytb6600github.h>
#include <math.h>

/* ============================================================================
 * PRIVATE HELPERS
 * ============================================================================ */

/**
 * @brief  Read the input clock frequency for the timer associated with hs->htim.
 *
 * STM32F446RE timer clocks:
 *   - APB1 timers (TIM2/3/4/5/6/7/12/13/14): PCLK1 x (1 or 2 depending on PSC)
 *   - APB2 timers (TIM1/8/9/10/11):          PCLK2 x (1 or 2 depending on PSC)
 *
 * This function queries HAL RCC to get actual values — making the library
 * resilient to any clock tree configuration user chose in CubeMX.
 */
static uint32_t Stepper_GetTimerClockHz(TIM_HandleTypeDef *htim)
{
    uint32_t pclk_freq;
    uint32_t apb_prescaler;
    RCC_ClkInitTypeDef clk_cfg;
    uint32_t flash_latency;

    HAL_RCC_GetClockConfig(&clk_cfg, &flash_latency);

    /* Determine which APB bus this timer is on.
     * On F446: TIM1, TIM8, TIM9, TIM10, TIM11 are on APB2. Others on APB1. */
    TIM_TypeDef *tim = htim->Instance;
    bool is_apb2 = (tim == TIM1 || tim == TIM8 ||
                    tim == TIM9 || tim == TIM10 || tim == TIM11);

    if (is_apb2) {
        pclk_freq     = HAL_RCC_GetPCLK2Freq();
        apb_prescaler = clk_cfg.APB2CLKDivider;
    } else {
        pclk_freq     = HAL_RCC_GetPCLK1Freq();
        apb_prescaler = clk_cfg.APB1CLKDivider;
    }

    /* If APB prescaler is 1 -> timer clk = PCLK.
     * If APB prescaler is not 1 -> timer clk = PCLK x 2 (STM32 rule). */
    uint32_t timer_clk = (apb_prescaler == RCC_HCLK_DIV1) ? pclk_freq
                                                          : (pclk_freq * 2U);
    return timer_clk;
}

/**
 * @brief  Given a desired PWM frequency and timer input clock, compute
 *         PSC and ARR that produce the closest match with 50% duty support.
 *
 * Strategy: pick smallest PSC such that ARR fits in 16-bit (TIM3/4 are 16-bit,
 * TIM2/5 are 32-bit on F446 — we stay in 16-bit range for portability).
 *
 * Returns true on success, false if target frequency not achievable.
 */
static bool Stepper_ComputePscArr(uint32_t tim_clk_hz,
                                  uint32_t target_freq_hz,
                                  uint32_t *psc_out,
                                  uint32_t *arr_out)
{
    if (target_freq_hz == 0U) return false;

    /* For 16-bit compatibility: ARR max = 65535.
     * period_ticks = tim_clk / target_freq
     * We want: (PSC+1) * (ARR+1) = period_ticks
     * Pick PSC so that ARR+1 >= 100 (for duty-cycle resolution) and <= 65536. */

    uint64_t period_ticks = (uint64_t)tim_clk_hz / target_freq_hz;
    if (period_ticks < 2ULL) return false; /* Frequency too high */

    uint32_t psc = 0U;
    uint32_t arr_plus_1 = (uint32_t)period_ticks;

    while (arr_plus_1 > 65536U) {
        psc++;
        arr_plus_1 = (uint32_t)(period_ticks / (psc + 1U));
        if (psc > 65535U) return false; /* Frequency too low */
    }

    *psc_out = psc;
    *arr_out = arr_plus_1 - 1U;
    return true;
}

static uint16_t Stepper_PulsesPerRev(Stepper_MicrostepMode_t mode)
{
    switch (mode) {
        case STEPPER_MICROSTEP_FULL:   return 200U;
        case STEPPER_MICROSTEP_HALF_A: return 400U;
        case STEPPER_MICROSTEP_HALF_B: return 400U;
        default:                       return 200U;
    }
}

/* ============================================================================
 * PUBLIC API IMPLEMENTATION
 * ============================================================================ */

Stepper_Status_t Stepper_Init(Stepper_Handle_t *hs)
{
    if (hs == NULL || hs->htim == NULL) return STEPPER_ERR_NULL;

    /* Cache the timer clock — this is the cornerstone of flexibility.
     * User can change clock tree in CubeMX and this still works. */
    hs->timer_clock_hz = Stepper_GetTimerClockHz(hs->htim);
    if (hs->timer_clock_hz == 0U) return STEPPER_ERR_TIM_CONFIG;

    /* Default state */
    hs->microstep      = STEPPER_MICROSTEP_FULL;
    hs->pulses_per_rev = Stepper_PulsesPerRev(hs->microstep);
    hs->current_rpm    = 0.0f;
    hs->running        = false;

    /* Make sure motor is disabled and direction is known */
    Stepper_Enable(hs, false);
    Stepper_SetDirection(hs, STEPPER_DIR_CW);

    hs->initialized = true;
    return STEPPER_OK;
}

Stepper_Status_t Stepper_SetMicrostep(Stepper_Handle_t *hs,
                                      Stepper_MicrostepMode_t mode)
{
    if (hs == NULL || !hs->initialized) return STEPPER_ERR_NULL;
    if (mode != STEPPER_MICROSTEP_FULL &&
        mode != STEPPER_MICROSTEP_HALF_A &&
        mode != STEPPER_MICROSTEP_HALF_B) {
        return STEPPER_ERR_RANGE;
    }

    hs->microstep      = mode;
    hs->pulses_per_rev = Stepper_PulsesPerRev(mode);

    /* If already running, recompute PWM frequency for new pulses/rev
     * so that RPM stays consistent. */
    if (hs->running && hs->current_rpm > 0.0f) {
        return Stepper_SetSpeedRPM(hs, hs->current_rpm);
    }
    return STEPPER_OK;
}

Stepper_Status_t Stepper_SetDirection(Stepper_Handle_t *hs,
                                      Stepper_Direction_t dir)
{
    if (hs == NULL) return STEPPER_ERR_NULL;
    HAL_GPIO_WritePin(hs->dir_port, hs->dir_pin,
                      (dir == STEPPER_DIR_CW) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    /* TB6600 needs >= 5 us DIR setup before next PUL edge.
     * If you call this right before Start() at 100+ kHz pulse rate,
     * consider adding a small delay. For typical use cases it's fine. */
    return STEPPER_OK;
}

Stepper_Status_t Stepper_SetSpeedRPM(Stepper_Handle_t *hs, float rpm)
{
    if (hs == NULL || !hs->initialized) return STEPPER_ERR_NULL;
    if (rpm < 0.0f) return STEPPER_ERR_RANGE;

    if (rpm == 0.0f) {
        hs->current_rpm = 0.0f;
        return Stepper_Stop(hs);
    }

    /* Convert RPM to pulse frequency:
     *   f_pulse = (RPM / 60) * pulses_per_rev                      */
    float freq_f = (rpm / 60.0f) * (float)hs->pulses_per_rev;
    uint32_t target_freq = (uint32_t)roundf(freq_f);

    if (target_freq < TB6600_MIN_PULSE_FREQ_HZ ||
        target_freq > TB6600_MAX_PULSE_FREQ_HZ) {
        return STEPPER_ERR_RANGE;
    }

    uint32_t psc, arr;
    if (!Stepper_ComputePscArr(hs->timer_clock_hz, target_freq, &psc, &arr)) {
        return STEPPER_ERR_TIM_CONFIG;
    }

    /* Apply new PSC/ARR and set 50% duty cycle.
     * 50% duty at <= 100 kHz gives pulse width >= 5 us, well above
     * TB6600's 2.2 us minimum. */
    __HAL_TIM_SET_PRESCALER(hs->htim, psc);
    __HAL_TIM_SET_AUTORELOAD(hs->htim, arr);
    __HAL_TIM_SET_COMPARE(hs->htim, hs->tim_channel, (arr + 1U) / 2U);

    /* Force update so PSC takes effect immediately without glitch.
     * Note: generating UEV resets counter; safe because TB6600 only
     * cares about rising edges. */
    hs->htim->Instance->EGR = TIM_EGR_UG;

    hs->current_rpm = rpm;
    return STEPPER_OK;
}

Stepper_Status_t Stepper_Start(Stepper_Handle_t *hs)
{
    if (hs == NULL || !hs->initialized) return STEPPER_ERR_NULL;
    if (hs->current_rpm == 0.0f) return STEPPER_ERR_RANGE;

    if (HAL_TIM_PWM_Start(hs->htim, hs->tim_channel) != HAL_OK) {
        return STEPPER_ERR_HAL;
    }
    hs->running = true;
    return STEPPER_OK;
}

Stepper_Status_t Stepper_Stop(Stepper_Handle_t *hs)
{
    if (hs == NULL || !hs->initialized) return STEPPER_ERR_NULL;
    if (HAL_TIM_PWM_Stop(hs->htim, hs->tim_channel) != HAL_OK) {
        return STEPPER_ERR_HAL;
    }
    hs->running = false;
    return STEPPER_OK;
}

Stepper_Status_t Stepper_Enable(Stepper_Handle_t *hs, bool enable)
{
    if (hs == NULL) return STEPPER_ERR_NULL;
    GPIO_PinState state;
    if (hs->ena_active_low) {
        state = enable ? GPIO_PIN_RESET : GPIO_PIN_SET;
    } else {
        state = enable ? GPIO_PIN_SET   : GPIO_PIN_RESET;
    }
    HAL_GPIO_WritePin(hs->ena_port, hs->ena_pin, state);
    return STEPPER_OK;
}

Stepper_Status_t Stepper_GetMaxRPM(const Stepper_Handle_t *hs, float *max_rpm_out)
{
    if (hs == NULL || max_rpm_out == NULL || !hs->initialized) {
        return STEPPER_ERR_NULL;
    }
    /* max_rpm = (max_pulse_freq / pulses_per_rev) * 60 */
    *max_rpm_out = ((float)TB6600_MAX_PULSE_FREQ_HZ /
                    (float)hs->pulses_per_rev) * 60.0f;
    return STEPPER_OK;
}
