'use client'
import React, { useState, useEffect } from 'react';
import { AppBar, Toolbar, Typography, Card, CardActions, CardContent, Button, FormControl, InputLabel, Select, MenuItem } from '@mui/material';
import DataSet from "../../public/test_results.json";
import ReactJsonViewCompare from 'react-json-view-compare';

export default function Home() {
  const [data, setData] = useState('');
  const [showText, setShowText] = useState('');
  const [optionDS, setOptionDS] = useState('');
  const handleChange = (event) => {
    let selected = event.target.value;
    let dataSelected = data[selected]
    setOptionDS(selected);
    setShowText(dataSelected)
    // console.log(deepDiff.diff(dataSelected[1], dataSelected[2]))
  };
  useEffect(() => {
    // Create a new object to store the updated DATA
    const updatedData = {};

    DataSet.forEach((d) => {
      const reaction_id = d.data.reaction_id;
      const input_text = d.data.input_text;
      const truth = d.data.output_reaction_inputs;

      let infer = null;
      try {
        infer = JSON.parse(d.completion).output_reaction_inputs;
      } catch (error) {
        // Handle JSON parsing error
      }

      const link = `https://open-reaction-database.org/client/id/${reaction_id}`;

      updatedData[reaction_id] = [input_text, truth, infer, link];
    });

    console.log(updatedData)
    setData(updatedData);
  }, []);
  return (
    <div>
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6">Organic Synthesis Parser</Typography>
        </Toolbar>
      </AppBar>
      <main>
        <Card sx={{ m: 2, padding: 1 }}>
          <CardContent>
            <Typography gutterBottom variant="h5" component="div">
              Text
            </Typography>
            <FormControl fullWidth>
              <InputLabel id="dataset-label">DataSet</InputLabel>
              <Select
                labelId='dataset-label'
                value={optionDS}
                label="DataSet"
                onChange={handleChange}
              >
                {Object.keys(data).map((option) => (
                  <MenuItem key={option} value={option}>
                    {option}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            {showText && (
              <>
                <Typography sx={{ mt: 2 }} gutterBottom component="div">
                  {showText[0]}
                </Typography>
                <Typography sx={{ mt: 2 }} gutterBottom component="div">
                  <a href={showText[3]} target='blank'>Link</a>
                </Typography>
              </>
            )}
          </CardContent>
          <CardActions>
            <Button size="small">Learn More</Button>
          </CardActions>
        </Card>
        <ReactJsonViewCompare oldData={showText[1]} newData={showText[2]} />
      </main>
    </div>
  );
}