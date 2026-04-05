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
import { onMounted, ref } from 'vue';
import { QWebChannel } from 'qwebchannel';
import { SocketService } from './websocket.js';

const ws = new SocketService('ws://127.0.0.1:8765');
const canvasRef = ref(null);
const currentSubtitle = ref("");
const activeExpressions = ref(new Set());
let subtitleTimer = null;

let app = null;
let model = null;
let backgroundSprite = null;
let web_bridget = null;
window.offset_y = 0; 


window.MouthParam="ParamMouthOpenY"

const showSubtitle = (text) => {
  currentSubtitle.value = text;
  if (subtitleTimer) clearTimeout(subtitleTimer);
  const duration = Math.max(1500, text.length * 200);
  subtitleTimer = setTimeout(() => { currentSubtitle.value = ""; }, duration);
};

window.loadBackground = (imagePath) => {
  console.log("🎨 正在更换背景:", imagePath);
  if (!window.backgroundSprite) {
      console.error("❌ backgroundSprite 尚未初始化");
      return;
  }

  try {
    const newTexture = PIXI.Texture.from(imagePath);
    
    const applyResize = () => {
      const scale = Math.max(app.screen.width / newTexture.width, app.screen.height / newTexture.height);
      window.backgroundSprite.texture = newTexture;
      window.backgroundSprite.scale.set(scale);
      window.backgroundSprite.x = app.screen.width / 2;
      window.backgroundSprite.y = app.screen.height / 2;
      console.log("✅ 背景渲染完成");
    };

    if (newTexture.baseTexture.valid) {
      applyResize();
    } else {
      newTexture.once('update', applyResize);
    }
  } catch (e) { 
    console.error("背景更换失败:", e); 
  }
};

window.loadModel = async (modelPath,mouthparam) => {
  window.MouthParam=mouthparam
  console.log("👗 正在更换模型:", modelPath,window.MouthParam);
  try {
    if (model) {
      app.stage.removeChild(model);
      model.destroy(true);
    }
    model = await PIXI.live2d.Live2DModel.from(modelPath);
    window.model = model;
    app.stage.addChild(model);
    
    model.scale.set(0.16);
    model.anchor.set(0.5, 0.5);
    
    await model.internalModel.coreModel.setParameterValueById('Param123', 1.0);
    window.resizeModel(); 
    console.log("✅ 模型加载成功");
  } catch (e) { console.error("模型加载失败:", e); }
};

window.resizeModel = (offset = null) => {
  if (!model) return;
  if (offset !== null) window.offset_y = offset;
  model.x = app.screen.width / 3;
  model.y = app.screen.height * 1.1 - window.offset_y; 
};

window.CLEAR = () => {
  console.log("Web正在释放资源...");
  if (model) model.destroy(true, { children: true, texture: true });
  if (app) app.destroy(true, { children: true, texture: true });
  if (web_bridget) web_bridget.web_done_set();
};

function initInteractions() {
  app.stage.interactive = true;
  app.stage.hitArea = app.screen;
  let dragData = null;
  let offset = { x: 0, y: 0 };

  app.stage.on('pointerdown', (event) => {
    if (!model) return;
    dragData = event.data;
    const pos = dragData.getLocalPosition(model.parent);
    offset.x = pos.x - model.x;
    offset.y = pos.y - model.y;
  });

  app.stage.on('pointermove', () => {
    if (dragData && model) {
      const pos = dragData.getLocalPosition(model.parent);
      model.x = pos.x - offset.x;
      model.y = pos.y - offset.y;
    }
  });

  app.stage.on('pointerup', () => { dragData = null; });

  window.addEventListener('wheel', (event) => {
    if (!model) return;
    const factor = Math.pow(1.1, event.deltaY > 0 ? -1 : 1);
    model.scale.set(Math.max(0.05, Math.min(2.0, model.scale.x * factor)));
  }, { passive: false });
}

async function initLive2D() {
  app = new PIXI.Application({
    view: canvasRef.value,
    autoStart: true,
    resizeTo: window,
    // backgroundAlpha: 1,
    antialias: true,
    transparent: true,
    preserveDrawingBuffer: true
  });

  window.app = app;
  backgroundSprite = new PIXI.Sprite(PIXI.Texture.EMPTY);
  backgroundSprite.anchor.set(0.5);
  app.stage.addChildAt(backgroundSprite, 0);

  window.backgroundSprite = backgroundSprite;
  app.renderer.on('resize', () => {
    if (backgroundSprite && backgroundSprite.texture.baseTexture.valid) {
        window.loadBackground(backgroundSprite.texture.baseTexture.resource.url);
    }
    window.resizeModel();
  });
  initInteractions();
}

let lastLipAmplitude = 0;

onMounted(async () => {
  await initLive2D();

  ws.onMessage(async (type, data) => {
    if (!model) return;

    if (type === "expression") {
      const manager = model.internalModel.motionManager.expressionManager;
      try {
        let targetName = data;
        if (activeExpressions.value.has(data)) {
          targetName = "re_" + data;
          activeExpressions.value.delete(data);
        } else {
          activeExpressions.value.add(data);
        }
        await manager.setExpression(targetName);
      } catch (err) { console.error("表情切换失败:", err); }
    } 
    else if (type === "lip") {
      if (!model) return;
      if (window.MouthParam=="ParamMouthOpenY"){
        const power = data.value;
        model.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', power, 0.8);
        model.internalModel.coreModel.setParameterValueById('ParamMouthForm', 0.5, 0.8);
        model.internalModel.coreModel.update();
      }else {
        const rawVal = Number(data.value) || 0;
        let amplitude = Math.pow(rawVal, 0.4) * 2.2; 
        if (amplitude < lastLipAmplitude) {
            amplitude = lastLipAmplitude * 0.85 + amplitude * 0.15;
        }
        lastLipAmplitude = amplitude;
        const core = model.internalModel.coreModel;
        const finalVal = Math.min(amplitude, 1.2);
        core.setParameterValueById('ParamA', finalVal, 0.8);
        core.setParameterValueById('ParamMouthOpenY', finalVal, 0.8);
        core.setParameterValueById('ParamMouthForm', 0.2 + finalVal * 0.3, 0.8);
        model.internalModel.coreModel.update();
      }
    }
    else if (type === "text" && data) {
      showSubtitle(data);
    }
  });

  ws.connect();

  if (window.qt && window.qt.webChannelTransport) {
    new QWebChannel(window.qt.webChannelTransport, (channel) => {
      web_bridget = channel.objects.web_bridget;
      console.log("✅ WebChannel 连接成功");
    });
  }
  if (web_bridget) {
      web_bridget.web_ready();
      console.log("🚀 前端已完全就绪，可以加载模型了");
  }
});
</script>