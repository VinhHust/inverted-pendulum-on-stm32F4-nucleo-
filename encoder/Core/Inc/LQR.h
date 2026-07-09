#ifndef INC_LQR_H_
#define INC_LQR_H_

#include "thucdonencoder.h"
#include "HBS57.h"

typedef enum
{ //4 phase
	KICK_START, //0
	SWING_UP,//1
	IDLE_PENDULUM,//2
	LQR_CONTROL//3
}pendulum_state;

typedef struct
{
	//các con trỏ ở đây tác động thẳng tới struct gốc chứ ko cần khai báo 1 biến mới cho struct

	pendulum_state state;
	Stepper_Handle_t* stepper;	 //con trỏ tới struct chứa các tham số của động cơ
	EncoderTypeDef *pend_enc; //con trỏ tới struct chứa các biến của encoder cho pend
	CartEncoderTypeDef *cart_enc; //con trỏ tới struct chứa các biến của encoder cho cart
	float current_accel;
}InvertedPendulumTypeDef;


//hàm khởi tạo trạng thái ban đầu của con lắc
//pendulum là con trỏ trỏ
void init_pendulum(InvertedPendulumTypeDef* pendulum);

//hàm tín toán LQR và điều khiển động cơ, gọi trong ngắt lấy mẫu
float run_pendulum(InvertedPendulumTypeDef* pendulum);


#endif /* INC_LQR_H_ */
