<template>
  <div id="live2d-container">
    <canvas id="live2d-canvas" ref="canvasRef"></canvas>
    
    <transition name="subtitle-fade">
      <div v-if="currentSubtitle" class="subtitle-overlay">
        <span class="subtitle-text">{{ currentSubtitle }}</span>
      </div>
    </transition>
  </div>
</template>

<style scoped>
#live2d-container {
  position: relative; 
  width: 100%;
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: hidden;
}

#live2d-canvas {
  width: 100%;
  height: 100%;
}

.subtitle-overlay {
  position: absolute;
  bottom: 15%; 
  width: 90%;
  text-align: center;
  pointer-events: none; 
  z-index: 999;
}

.subtitle-text {
  background: rgba(0, 0, 0, 0.5); 
  color: white;
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 20px;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
  display: inline-block;
  max-width: 80%;
  line-height: 1.5;
}

.subtitle-fade-enter-active, .subtitle-fade-leave-active {
  transition: all 0.4s ease;
}
.subtitle-fade-enter, .subtitle-fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>

<script setup>
import { onMounted,onBeforeUnmount,watch, ref } from 'vue';
import { QWebChannel } from 'qwebchannel'
import {SocketService} from './websocket.js'

const ws=new SocketService('ws://127.0.0.1:8765')
const canvasRef = ref(null);

const currentSubtitle = ref("");
let subtitleTimer = null;

let app;
let model;
let web_bridget=null

const showSubtitle = (text) => {
  currentSubtitle.value = text;
  
  if (subtitleTimer) clearTimeout(subtitleTimer);
  
  const duration = Math.max(500, text.length * 200);
  
  subtitleTimer = setTimeout(() => {
    currentSubtitle.value = "";
  }, duration);
};

window.CLEAR=()=>{
  console.log("Web正在释放资源...")
  if(model){
    model.destroy(true, { children: true, texture: true });
    console.log("✅ 模型已销毁");
  }
  if(app){
    app.destroy(true, { children: true, texture: true });
    console.log("✅ 渲染已关闭");
  }
  if(web_bridget){
    console.log("📡 Web发出清除结束信号")
    web_bridget.web_done_set()
  }
}

function initInteractions() {
  app.stage.interactive = true;
  app.stage.hitArea = app.screen;

  let dragData = null;
  let offset = { x: 0, y: 0 };

  app.stage.on('pointerdown', (event) => {
    dragData = event.data;
    const newPosition = dragData.getLocalPosition(model.parent);
    offset.x = newPosition.x - model.x;
    offset.y = newPosition.y - model.y;
  });

  app.stage.on('pointermove', () => {
    if (dragData) {
      const newPosition = dragData.getLocalPosition(model.parent);
      model.x = newPosition.x - offset.x;
      model.y = newPosition.y - offset.y;
    }
  });

  app.stage.on('pointerup', () => { dragData = null; });

  window.addEventListener('wheel', (event) => {
    const zoomIntensity = 0.1;
    const scrollDirection = event.deltaY > 0 ? -1 : 1;
    const factor = Math.pow(1 + zoomIntensity, scrollDirection);
    let newScale = model.scale.x * factor;
    model.scale.set(Math.max(0.05, Math.min(2.0, newScale)));
  }, { passive: false });
}

window.offset_y = 0;

async function initLive2D() {
  app = new PIXI.Application({
    view: canvasRef.value,
    autoStart: true,
    resizeTo: window,
    backgroundAlpha: 1,
    antialias: true,
    preserveDrawingBuffer: true
  });

  try {
    const backgroundSprite=PIXI.Sprite.from("background/bk4.png");
    backgroundSprite.anchor.set(0.5);
    app.stage.addChild(backgroundSprite);

    const resizeBackground = () => {
        if (!backgroundSprite || !backgroundSprite.texture.valid) return;
        const screenWidth = app.screen.width;
        const screenHeight = app.screen.height;
        const scale = Math.max(screenWidth / backgroundSprite.texture.width, screenHeight / backgroundSprite.texture.height);
        backgroundSprite.scale.set(scale);
        backgroundSprite.x = screenWidth / 2;
        backgroundSprite.y = screenHeight / 2;
    };

    if (backgroundSprite.texture.baseTexture.valid) {
        resizeBackground();
    } else {
        backgroundSprite.texture.once('update', resizeBackground);
    }

    model = await PIXI.live2d.Live2DModel.from("models/QianYi/QianYi.model3.json");
    window.model=model
    app.stage.addChild(model);

    model.scale.set(0.16);
    model.anchor.set(0.5, 0.5);

    const resizeModel = (offset=null) => {
        if (!model) return;

        if (offset!=null){window.offset_y=offset}

        console.log(window.offset_y)
        model.x = app.screen.width / 3;
        model.y = app.screen.height * 1.1-window.offset_y; 
    };
    window.resizeModel = resizeModel;

    setTimeout(() => {
    console.log("📏 延迟校准位置...");
    resizeModel(); 
    }, 100);

    const onResize = () => {
        requestAnimationFrame(() => {
            resizeBackground();
            resizeModel();
        });
    };
    app.renderer.on('resize', onResize);

    await model.internalModel.coreModel.setParameterValueById('Param123', 1.0);
    initInteractions();

  } catch (error) {
    console.error("❌ 加载失败：", error);
  }
}

const activeExpressions = ref(new Set());
onMounted(async () => {
  await initLive2D();
  console.log("web初始化成功")

  ws.onMessage(async (type, data) => {
    if (type == "expression" && model){
      const manager = model.internalModel.motionManager.expressionManager;
      const settings = model.internalModel.settings.expressions;

      try {
        let targetName = data;

        if (activeExpressions.value.has(data)) {
          console.log(`🧼 [取消叠加] 发送重置信号: re_${data}`);
          targetName = "re_" + data;
          activeExpressions.value.delete(data);
        } else {
          console.log(`🎭 [新增叠加] 发送激活信号: ${data}`);
          activeExpressions.value.add(data);
        }

        await manager.setExpression(targetName);

        console.log("📊 当前激活表情池:", Array.from(activeExpressions.value));
        console.log("✅ Expression 切换成功");

      } catch (err) {
        console.error("💥 setExpression 环节崩溃:", err);
      }
    }
    else if (type === "lip" && model) {
    const power = data.value;

    model.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', power, 0.8);
    model.internalModel.coreModel.setParameterValueById('ParamMouthForm', 0.5, 0.8);

    model.internalModel.coreModel.update();
    }
    else if(type=="text"&&data){
      showSubtitle(data)
    }
  });

  ws.connect()

  if (window.qt && window.qt.webChannelTransport){
    new QWebChannel(window.qt.webChannelTransport,(channel)=>{
      web_bridget=channel.objects.web_bridget;
      console.log("✅ WebChannel 连接成功");
    })
  }
});

</script>
